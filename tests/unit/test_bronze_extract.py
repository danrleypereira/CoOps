"""
Testes unitários para o módulo bronze_extract.

Testa a orquestração da extração da camada Bronze. Desde o wiring do #30,
a extração em si é `BronzeService` (patcheada aqui como a fronteira que é);
estes testes fixam a composição: o que o CLI passa ao serviço e aos
extratores legados que ficaram (members #238, issue events #239), a ordem
dos passos, o sweep de agregados #170 e o caminho de erro.
"""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _extraction_mocks():
    """Patch every extraction collaborator of ``run_extraction`` at once.

    The service and the adapter are patched where the composition imports
    them (``coops.etl.bronze_extract``); the two legacy extractors are
    patched at their own modules, because ``run_extraction`` imports them
    at call time. Returns a namespace of the mocks.
    """
    with ExitStack() as stack:
        service_cls = stack.enter_context(
            patch('coops.etl.bronze_extract.BronzeService')
        )
        service = service_cls.return_value
        service.extract_repositories.return_value = [
            'repositories_raw', 'repositories_filtered',
            'repositories_detailed', 'repo_one',
        ]
        service.extract_issues.return_value = ['issues_one', 'prs_one']
        service.extract_commits.return_value = ['commits_one']
        service.extract_structures.return_value = ['structure_one']
        adapter_cls = stack.enter_context(
            patch('coops.etl.bronze_extract.GitHubSourceAdapter')
        )
        events = stack.enter_context(
            patch(
                'coops.bronze.issues.extract_issue_events',
                return_value=['data/bronze/issue_events_one.json'],
            )
        )
        members = stack.enter_context(
            patch(
                'coops.bronze.members.extract_members',
                return_value=[
                    'data/bronze/members_basic.json',
                    'data/bronze/members_detailed.json',
                ],
            )
        )
        registry = stack.enter_context(
            patch('coops.etl.bronze_extract.update_data_registry')
        )
        client_cls = stack.enter_context(
            patch('coops.etl.bronze_extract.GitHubAPIClient')
        )
        yield SimpleNamespace(
            service_cls=service_cls,
            service=service,
            adapter_cls=adapter_cls,
            events=events,
            members=members,
            registry=registry,
            client_cls=client_cls,
        )


class TestBronzeExtract:
    """Testes para o script bronze_extract"""

    @pytest.fixture(autouse=True)
    def _isolated_settings(self, monkeypatch):
        """github_token/github_org agora vêm de coops.infrastructure.get_settings()
        (lru_cache'd process-wide), então cada teste define o env necessário e
        limpa o cache antes/depois pra não vazar entre testes."""
        from coops.infrastructure.config import get_settings
        monkeypatch.delenv("COOPS_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("COOPS_ORG", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        get_settings.cache_clear()
        # Three run-end steps touch ./data/bronze and are patched out for every
        # test in this class: in the fork's checkout data/bronze is the
        # committed, published corpus, and a test run must never mutate it —
        # the fence applies to the suite too. The orphan reconciliation
        # (#216) deletes files there; the dedupe report (#248) writes
        # data/bronze/dedupe.json there; the #170 aggregate sweep unlinks
        # <family>_all.json there. Each has its own wiring test in
        # TestBronzeDedupeWiring / TestBronzeAggregateSweep / the reconcile
        # module's tests, which run them against tmp_path trees.
        with patch('coops.etl.bronze_extract.reconcile_orphans') as mock_reconcile, \
             patch('coops.etl.bronze_extract._report_bronze_dedupe') as mock_dedupe, \
             patch('coops.etl.bronze_extract._retire_bronze_aggregates') as mock_sweep:
            mock_reconcile.return_value = None
            mock_dedupe.return_value = None
            mock_sweep.return_value = None
            yield mock_reconcile
        get_settings.cache_clear()

    @pytest.fixture
    def wired(self):
        yield from _extraction_mocks()

    def test_main_extracts_all_layers(self, wired, capsys):
        """Testa que main extrai todas as camadas Bronze"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "Starting Bronze layer extraction" in captured.out
        assert "Extracting repositories" in captured.out
        assert "Extracting issues and pull requests" in captured.out
        assert "Extracting commits" in captured.out
        assert "Extracting organization members" in captured.out
        assert "Extracting repository structures" in captured.out
        assert "Bronze extraction completed" in captured.out

    def test_main_with_org_from_settings(self, wired, capsys, monkeypatch):
        """Testa que main usa o github_org vindo de Settings (env GITHUB_ORG)"""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_ORG", "my-org")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "organization: my-org" in captured.out

    def test_main_with_cache_flag(self, wired):
        """Testa que main passa o flag --cache para o adaptador e para os
        extratores legados que ficaram no caminho."""
        with patch('sys.argv', ['bronze_extract.py', '--cache']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            # Verify use_cache=True was passed
            assert wired.adapter_cls.call_args[1]['use_cache'] is True
            assert wired.events.call_args[1]['use_cache'] is True
            assert wired.members.call_args[1]['use_cache'] is True

    def test_main_with_max_commits_per_repo(self, wired):
        """Testa que main aceita --max-commits-per-repo"""
        with patch('sys.argv', ['bronze_extract.py', '--max-commits-per-repo', '1000']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_commits.call_args[1]['max_commits_per_repo'] == 1000

    def test_main_with_max_repos(self, wired):
        """Testa que main aceita --max-repos e repassa pro serviço"""
        with patch('sys.argv', ['bronze_extract.py', '--max-repos', '3']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_repositories.call_args[1]['max_repos'] == 3

    @pytest.mark.parametrize("flag", ["--max-repos", "--max-issues", "--max-prs", "--max-commits-per-repo"])
    @pytest.mark.parametrize("value", ["0", "-1", "abc"])
    def test_main_rejects_non_positive_caps(self, flag, value, capsys):
        """Um cap 0 ou negativo não buscaria nada: argparse rejeita antes de chamar a API"""
        with patch('sys.argv', ['bronze_extract.py', flag, value]), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            from coops.etl import bronze_extract

            with pytest.raises(SystemExit) as exc_info:
                bronze_extract.main()

        assert exc_info.value.code == 2
        assert flag in capsys.readouterr().err
        mock_client_cls.assert_not_called()

    def test_main_without_max_repos_defaults_to_none(self, wired):
        """Testa que --max-repos é None quando não passado (sem cap)"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_repositories.call_args[1]['max_repos'] is None

    def test_main_with_max_issues_and_max_prs(self, wired):
        """Testa que main aceita --max-issues e --max-prs e repassa pro serviço"""
        with patch('sys.argv', ['bronze_extract.py', '--max-issues', '5', '--max-prs', '3']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_issues.call_args[1]['max_issues'] == 5
            assert wired.service.extract_issues.call_args[1]['max_prs'] == 3

    def test_main_without_max_issues_and_max_prs_defaults_to_none(self, wired):
        """Testa que --max-issues/--max-prs são None quando não passados (sem cap)"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_issues.call_args[1]['max_issues'] is None
            assert wired.service.extract_issues.call_args[1]['max_prs'] is None

    def test_main_displays_all_files(self, wired, capsys):
        """Testa que main exibe todos os arquivos gerados"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        # 4 repository entities + 2 issues/prs + 1 events file + 1 commit +
        # 2 member files + 1 structure.
        assert "Total files generated: 11" in captured.out
        assert "Repositories: 4" in captured.out
        assert "Issues/PRs: 2" in captured.out
        assert "Issue events: 1" in captured.out
        assert "Commits: 1" in captured.out
        assert "Members: 2" in captured.out
        assert "Structures: 1" in captured.out

    def test_main_handles_extraction_error(self, wired, capsys):
        """Testa tratamento de erro durante extração"""
        wired.service.extract_repositories.side_effect = Exception("API Error")
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            with pytest.raises(SystemExit) as exc_info:
                bronze_extract.main()

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Bronze extraction failed" in captured.out
        assert "API Error" in captured.out

    def test_main_extracts_in_correct_order(self, wired):
        """Testa que as extrações são feitas na ordem correta"""
        order = []

        def track(name, result):
            def handler(*args, **kwargs):
                order.append(name)
                return result
            return handler

        wired.service.extract_repositories.side_effect = track('repos', ['repositories_raw'])
        wired.service.extract_issues.side_effect = track('issues', ['issues_one'])
        wired.events.side_effect = track('events', ['data/bronze/issue_events_one.json'])
        wired.service.extract_commits.side_effect = track('commits', ['commits_one'])
        wired.members.side_effect = track('members', ['data/bronze/members_basic.json'])
        wired.service.extract_structures.side_effect = track('structures', ['structure_one'])

        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        assert order == ['repos', 'issues', 'events', 'commits', 'members', 'structures']

    def test_main_skip_structure(self, wired):
        """--skip-structure não chama o passo de estruturas"""
        with patch('sys.argv', ['bronze_extract.py', '--skip-structure']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            wired.service.extract_structures.assert_not_called()
            wired.service.extract_commits.assert_called_once()

    def test_main_displays_timestamp(self, wired, capsys):
        """Testa que main exibe timestamp de início"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "Started at:" in captured.out

    @pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "GITHUB_ORG"])
    def test_main_requires_github_token_and_org(self, monkeypatch, tmp_path, capsys, missing):
        """Testa que main requer GITHUB_TOKEN/GITHUB_ORG (via Settings, não mais --token/--org)
        e sai com erro legível em vez de traceback.
        Precisa isolar o cwd: um .secrets real na raiz do repo (com credenciais de
        verdade ou placeholders) seria lido pelo Settings() mesmo com os env vars
        removidos, mascarando a falta de configuração."""
        from coops.infrastructure.config import get_settings
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(missing, raising=False)
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            from coops.etl import bronze_extract

            with pytest.raises(SystemExit) as exc_info:
                bronze_extract.main()

        assert exc_info.value.code == 1
        assert "GITHUB_TOKEN and GITHUB_ORG must be set" in capsys.readouterr().err
        mock_client_cls.assert_not_called()

    def test_main_initializes_github_client(self, wired, capsys, monkeypatch):
        """Testa que main inicializa o GitHubAPIClient com o token vindo de Settings"""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "my-secret-token")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.client_cls.call_args[0][0] == 'my-secret-token'

        # Verifica que o processo foi concluído sem erro
        captured = capsys.readouterr()
        assert "Bronze extraction completed" in captured.out

    def test_main_creates_passes_and_saves_watermark_store(self, wired, monkeypatch):
        """main loads a WatermarkStore, threads it into the service and the
        events extractor, and saves it."""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.etl.bronze_extract.WatermarkStore') as mock_store_cls:
            store = mock_store_cls.return_value
            # main só grava o watermark numa execução
            # online; sem isso o mock teria offline
            # "verdadeiro" por acidente.
            wired.client_cls.return_value.offline = False
            from coops.etl import bronze_extract

            bronze_extract.main()

        mock_store_cls.assert_called_once()
        store.save.assert_called_once()
        assert wired.service_cls.call_args[1]['watermarks'] is store
        assert wired.events.call_args[1]['watermarks'] is store
        get_settings.cache_clear()

    def test_main_with_repo_flag(self, wired):
        """--repo é repetível e chega ao serviço como repo_filter"""
        with patch('sys.argv', ['bronze_extract.py', '--repo', 'coops-org/one', '--repo', 'coops-org/two']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_repositories.call_args[1]['repo_filter'] == ['coops-org/one', 'coops-org/two']

    def test_main_without_repo_defaults_to_none(self, wired):
        """Sem --repo, repo_filter é None (sem seleção)"""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.service.extract_repositories.call_args[1]['repo_filter'] is None

    def test_main_offline_flag(self, wired):
        """--offline chega ao cliente e ao serviço, e implica uso do cache"""
        with patch('sys.argv', ['bronze_extract.py', '--offline']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.client_cls.call_args[1]['offline'] is True
            # Offline implies reading the cache, even without an explicit
            # --cache — the composition passes use_cache=True through to
            # the adapter and the legacy extractors.
            assert wired.adapter_cls.call_args[1]['use_cache'] is True
            assert wired.service_cls.call_args[1]['offline'] is True

    def test_main_cache_dir_flag(self, wired):
        """--cache-dir chega ao construtor do cliente (o padrão é relativo ao cwd)"""
        with patch('sys.argv', ['bronze_extract.py', '--cache-dir', 'custom-cache']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.client_cls.call_args[1]['cache_dir'] == 'custom-cache'

    def test_main_cache_dir_defaults_to_cache(self, wired):
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert wired.client_cls.call_args[1]['cache_dir'] == 'cache'

    def test_main_registers_every_generated_file(self, wired):
        """The registry receives the data/bronze paths of every family."""
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

        (layer, kind, files), _ = wired.registry.call_args
        assert (layer, kind) == ('bronze', 'all_extractions')
        assert sorted(files) == sorted([
            'data/bronze/repositories_raw.json',
            'data/bronze/repositories_filtered.json',
            'data/bronze/repositories_detailed.json',
            'data/bronze/repo_one.json',
            'data/bronze/issues_one.json',
            'data/bronze/prs_one.json',
            'data/bronze/issue_events_one.json',
            'data/bronze/commits_one.json',
            'data/bronze/members_basic.json',
            'data/bronze/members_detailed.json',
            'data/bronze/structure_one.json',
        ])

    # ---------------------------------------------------------------
    # Reconciliation wiring (#216): main() passes the bronze directory
    # and the mode — and NOTHING else. The narrowing decision is the
    # FILE's (repositories_filtered.json carries its own completeness
    # provenance), never argv's, because the narrowed run and the
    # reconciliation need not be the same process. The assertions are on
    # the CALL, never on printed output.
    # ---------------------------------------------------------------

    def test_main_reports_without_deleting_by_default(self, wired, _isolated_settings):
        """A full run REPORTS the orphans; it does not remove them.

        The scheduled run surfacing the orphans is the fix; deleting them
        without anyone asking is a separate decision, and the flag is where
        it gets made (#244 review)."""
        wired.client_cls.return_value.offline = False
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            _isolated_settings.assert_called_once_with(
                "data/bronze", apply=False,
            )

    @pytest.mark.parametrize("argv", [
        ['--max-repos', '1'],           # the debugging shape that would wipe a corpus
        ['--repo', 'coops-org/one'],
        ['--offline'],
    ], ids=["max-repos", "repo", "offline"])
    def test_main_passes_no_narrowing_to_the_reconciliation(self, wired, _isolated_settings, argv):
        """--repo, --max-repos and --offline narrow the listing, and none of
        them reaches the reconciliation as an argument. An argv guard is a
        guard that is not there when it matters: run A caps and exits; run
        B reconciles with a clean argv and would delete every unlisted
        repository's files. The refusal must come from the listing's own
        provenance (tested in test_bronze_reconcile.py), so the call here
        is byte-for-byte the full run's call."""
        with patch('sys.argv', ['bronze_extract.py', *argv]):
            from coops.etl import bronze_extract

            bronze_extract.main()

            _isolated_settings.assert_called_once_with(
                "data/bronze", apply=False,
            )

    def test_main_deletes_nothing_without_the_apply_flag(self, wired, _isolated_settings):
        """THE DEFAULT RUN DELETES NOTHING.

        A routine that removes files must not remove them because nobody
        passed a flag: the mode you get by forgetting has to be the safe
        one. Reviewed onto #244 after the first implementation shipped
        ``apply=not --reconcile-dry-run``, which deleted by default and
        which every library-level test passed, because they called
        ``reconcile_orphans`` directly and never went through ``main``.
        """
        wired.client_cls.return_value.offline = False
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert _isolated_settings.call_args[1]["apply"] is False

    def test_main_reconcile_apply_flag_opts_in(self, wired, _isolated_settings):
        """--reconcile-apply is the only way deletion happens."""
        wired.client_cls.return_value.offline = False
        with patch('sys.argv', ['bronze_extract.py', '--reconcile-apply']):
            from coops.etl import bronze_extract

            bronze_extract.main()

            kwargs = _isolated_settings.call_args[1]
            assert kwargs["apply"] is True


class TestPersistWatermarks:
    """Offline replay (#199) não pode gravar watermark nenhum.

    Um replay lê o que o cache tem; um watermark derivado disso é uma
    afirmação sobre o estado do provedor que a execução não tem como
    sustentar. Gravá-lo é exatamente o mecanismo que transformou a leitura
    velha do #199 em corrupção durável.
    """

    def test_offline_writes_no_watermark_file(self, tmp_path):
        from coops.bronze.watermarks import WatermarkStore
        from coops.etl.bronze_extract import persist_watermarks
        from coops.utils.github_api import GitHubAPIClient

        client = GitHubAPIClient("token", cache_dir=str(tmp_path / "cache"), offline=True)
        path = tmp_path / "watermarks.json"
        store = WatermarkStore(str(path))
        store.update("org/repo1", last_updated_at="2026-09-23T18:48:10Z")

        persist_watermarks(store, client)

        assert not path.exists()

    def test_online_still_writes_the_file(self, tmp_path):
        # O controle de braços distintos: sem ele, um persist_watermarks
        # que nunca grava passaria no teste de cima e continuaria quebrado.
        from coops.bronze.watermarks import WatermarkStore
        from coops.etl.bronze_extract import persist_watermarks
        from coops.utils.github_api import GitHubAPIClient

        client = GitHubAPIClient("token", cache_dir=str(tmp_path / "cache"))
        path = tmp_path / "watermarks.json"
        store = WatermarkStore(str(path))
        store.update("org/repo1", last_updated_at="2026-09-23T18:48:10Z")

        persist_watermarks(store, client)

        reloaded = WatermarkStore(str(path))
        assert reloaded.get("org/repo1").last_updated_at == "2026-09-23T18:48:10Z"


class TestBronzeDedupeWiring:
    """#248: the run reports and PUBLISHES the by-id dedupe, every run.

    Lives outside ``TestBronzeExtract`` on purpose: that class's autouse
    fixture patches ``_report_bronze_dedupe`` out (it writes under
    ``./data/bronze``, which in the fork's checkout is the committed
    corpus), so the wiring is proven here instead, against a ``tmp_path``
    tree the test builds and a working directory the test owns.
    """

    @pytest.fixture(autouse=True)
    def _isolated_settings(self, monkeypatch, tmp_path):
        from coops.infrastructure.config import get_settings
        monkeypatch.delenv("COOPS_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("COOPS_ORG", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        # The extraction reads and writes ./data relative to the working
        # directory; owning one under tmp_path is what lets the REAL
        # _report_bronze_dedupe run here without touching the checkout.
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def wired(self):
        yield from _extraction_mocks()

    def _bronze(self, tmp_path):
        """The live pair, minimal: one recased repository, 7 days apart."""
        bronze = tmp_path / "data" / "bronze"
        bronze.mkdir(parents=True)
        repo = {
            "id": 957040204,
            "name": "x",
            "full_name": "unb-mds/x",
            "private": False,
        }
        for name, stamp in (("x", "2026-09-25T09:53:03+00:00"),
                            ("X", "2026-09-18T09:15:46")):
            document = {**repo, "name": name, "_metadata": {"extracted_at": stamp}}
            (bronze / f"repo_{name}.json").write_text(json.dumps(document), encoding="utf-8")
            payload = [{"_metadata": {"extracted_at": stamp}}, {"sha": "0" * 40}]
            (bronze / f"commits_{name}.json").write_text(json.dumps(payload), encoding="utf-8")
        return bronze

    def test_main_reports_and_publishes_the_dedupe(self, tmp_path, wired, capsys):
        """main() prints the dedupe section and writes
        data/bronze/dedupe.json naming the deduped id — the published
        metadata half of #248's output requirement."""
        from coops.etl import bronze_extract

        self._bronze(tmp_path)

        with patch('sys.argv', ['bronze_extract.py']):
            bronze_extract.main()

        out = capsys.readouterr().out
        assert "Bronze dedupe (by repository id, #248)" in out
        assert "deduped: commits id 957040204" in out

        published = json.loads((tmp_path / "data" / "bronze" / "dedupe.json").read_text(encoding="utf-8"))
        assert published["deduped"]["count"] >= 1
        families = {group["family"] for group in published["deduped"]["groups"]}
        assert "commits" in families
        (commits,) = [g for g in published["deduped"]["groups"] if g["family"] == "commits"]
        assert commits["repository_id"] == 957040204
        assert commits["kept"] == "commits_x.json"

    def test_main_publishes_the_refusal_not_just_the_dedupe(self, tmp_path, wired, capsys):
        """The arms-differ half: a pair 1h apart must reach the SAME two
        surfaces as a refusal — the run report and the published artifact —
        or a double-counted total ships unlabelled."""
        from coops.etl import bronze_extract

        bronze = self._bronze(tmp_path)
        # Make the pair young: rewrite the orphan's stamps to one hour
        # before the current file's.
        for filename in ("repo_X.json", "commits_X.json"):
            payload = json.loads((bronze / filename).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload["_metadata"]["extracted_at"] = "2026-09-25T08:53:03+00:00"
            else:
                payload[0]["_metadata"]["extracted_at"] = "2026-09-25T08:53:03+00:00"
            (bronze / filename).write_text(json.dumps(payload), encoding="utf-8")

        with patch('sys.argv', ['bronze_extract.py']):
            bronze_extract.main()

        out = capsys.readouterr().out
        assert "REFUSED — BOTH KEPT AND DOUBLE-COUNTED" in out
        assert "id 957040204" in out

        published = json.loads((tmp_path / "data" / "bronze" / "dedupe.json").read_text(encoding="utf-8"))
        assert published["refused_duplicates"]["count"] >= 1
        (commits,) = [
            g
            for g in published["refused_duplicates"]["groups"]
            if g["family"] == "commits"
        ]
        assert commits["repository_id"] == 957040204
        assert sorted(f["file"] for f in commits["files"]) == [
            "commits_X.json",
            "commits_x.json",
        ]


class TestBronzeAggregateSweep:
    """#170: the retired ``<family>_all.json`` aggregates are removed by the
    run itself, in the same run that writes the per-repository files.

    The sweep moved from the legacy extractors to the CLI with the #30
    wiring (``StoragePort`` has no delete), so this pins the CLI's sweep —
    against a ``tmp_path`` tree the test owns, for the same fence reason as
    ``TestBronzeDedupeWiring`` above.
    """

    @pytest.fixture(autouse=True)
    def _isolated_settings(self, monkeypatch, tmp_path):
        from coops.infrastructure.config import get_settings
        monkeypatch.delenv("COOPS_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("COOPS_ORG", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def wired(self):
        yield from _extraction_mocks()

    def test_run_removes_the_retired_aggregates_only(self, tmp_path, wired, capsys):
        from coops.etl import bronze_extract

        bronze = tmp_path / "data" / "bronze"
        silver = tmp_path / "data" / "silver"
        bronze.mkdir(parents=True)
        silver.mkdir()
        for family in ("commits", "issues", "prs", "issue_events"):
            (bronze / f"{family}_all.json").write_text("[]", encoding="utf-8")
        (bronze / "commits_repo1.json").write_text("[]", encoding="utf-8")
        # Silver's language_analysis_all.json shares the _all suffix, is a
        # different layer's artifact and is fetched by the dashboard: the
        # sweep must never widen to it.
        silver_sweep_target = silver / "language_analysis_all.json"
        silver_sweep_target.write_text("{}", encoding="utf-8")

        with patch('sys.argv', ['bronze_extract.py']):
            bronze_extract.main()

        for family in ("commits", "issues", "prs", "issue_events"):
            assert not (bronze / f"{family}_all.json").exists(), family
        assert (bronze / "commits_repo1.json").is_file()
        assert silver_sweep_target.is_file()
