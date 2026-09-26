"""
Testes unitários para o módulo bronze_extract.

Testa a orquestração da extração da camada Bronze.
"""

import json
from unittest.mock import patch

import pytest


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
        # Two run-end steps touch ./data/bronze and are patched out for every
        # test in this class: in the fork's checkout data/bronze is the
        # committed, published corpus, and a test run must never mutate it —
        # the fence applies to the suite too. The orphan reconciliation
        # (#216) deletes files there; the dedupe report (#248) writes
        # data/bronze/dedupe.json there. Both have their own wiring tests in
        # TestBronzeDedupeWiring / the reconcile module's tests, which run
        # them against tmp_path trees.
        with patch('coops.etl.bronze_extract.reconcile_orphans') as mock_reconcile, \
             patch('coops.etl.bronze_extract._report_bronze_dedupe') as mock_dedupe:
            mock_reconcile.return_value = None
            mock_dedupe.return_value = None
            yield mock_reconcile
        get_settings.cache_clear()

    def test_main_extracts_all_layers(self, capsys):
        """Testa que main extrai todas as camadas Bronze"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=['repo.json']), patch('coops.bronze.issues.extract_issues', return_value=['issues.json']), patch('coops.bronze.commits.extract_commits', return_value=['commits.json']), patch('coops.bronze.members.extract_members', return_value=['members.json']), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "Starting Bronze layer extraction" in captured.out
        assert "Extracting repositories" in captured.out
        assert "Extracting issues and pull requests" in captured.out
        assert "Extracting commits" in captured.out
        assert "Extracting organization members" in captured.out
        assert "Bronze extraction completed" in captured.out

    def test_main_with_org_from_settings(self, capsys, monkeypatch):
        """Testa que main usa o github_org vindo de Settings (env GITHUB_ORG)"""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_ORG", "my-org")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "organization: my-org" in captured.out


    def test_main_with_cache_flag(self):
        """Testa que main passa o flag --cache para os extractors"""
        with patch('sys.argv', ['bronze_extract.py', '--cache']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues') as mock_issues, patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members') as mock_members, patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_repos.return_value = []
            mock_issues.return_value = []
            mock_commits.return_value = []
            mock_members.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            # Verify use_cache=True was passed
            assert mock_repos.call_args[1]['use_cache'] is True
            assert mock_issues.call_args[1]['use_cache'] is True
            assert mock_commits.call_args[1]['use_cache'] is True
            assert mock_members.call_args[1]['use_cache'] is True

    def test_main_with_commits_method_graphql(self):
        """Testa que main aceita --commits-method graphql"""
        with patch('sys.argv', ['bronze_extract.py', '--commits-method', 'graphql']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['method'] == 'graphql'

    def test_main_with_time_range(self):
        """Testa que main aceita argumentos --since e --until"""
        with patch('sys.argv', ['bronze_extract.py',
                                '--since', '2024-01-01T00:00:00Z',
                                '--until', '2024-12-31T23:59:59Z']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['since'] == '2024-01-01T00:00:00Z'
            assert mock_commits.call_args[1]['until'] == '2024-12-31T23:59:59Z'

    def test_main_with_max_commits_per_repo(self):
        """Testa que main aceita --max-commits-per-repo"""
        with patch('sys.argv', ['bronze_extract.py', '--max-commits-per-repo', '1000']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['max_commits_per_repo'] == 1000

    def test_main_with_max_repos(self):
        """Testa que main aceita --max-repos e repassa pra extract_repositories"""
        with patch('sys.argv', ['bronze_extract.py', '--max-repos', '3']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_repos.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_repos.call_args[1]['max_repos'] == 3

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

    def test_main_without_max_repos_defaults_to_none(self):
        """Testa que --max-repos é None quando não passado (sem cap)"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_repos.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_repos.call_args[1]['max_repos'] is None

    def test_main_with_max_issues_and_max_prs(self):
        """Testa que main aceita --max-issues e --max-prs e repassa pra extract_issues"""
        with patch('sys.argv', ['bronze_extract.py', '--max-issues', '5', '--max-prs', '3']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues') as mock_issues, patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_issues.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_issues.call_args[1]['max_issues'] == 5
            assert mock_issues.call_args[1]['max_prs'] == 3

    def test_main_without_max_issues_and_max_prs_defaults_to_none(self):
        """Testa que --max-issues/--max-prs são None quando não passados (sem cap)"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues') as mock_issues, patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_issues.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_issues.call_args[1]['max_issues'] is None
            assert mock_issues.call_args[1]['max_prs'] is None

    def test_main_with_active_branches(self):
        """Testa que main aceita --include-active-branches e --active-days"""
        with patch('sys.argv', ['bronze_extract.py',
                                '--include-active-branches', '--active-days', '60']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['include_active_branches'] is True
            assert mock_commits.call_args[1]['active_days'] == 60

    def test_main_with_custom_page_size(self):
        """Testa que main aceita --commits-page-size"""
        with patch('sys.argv', ['bronze_extract.py', '--commits-page-size', '100']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['page_size'] == 100

    def test_main_with_time_chunks(self):
        """Testa que main aceita --time-chunks"""
        with patch('sys.argv', ['bronze_extract.py', '--time-chunks', '5']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits') as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_commits.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_commits.call_args[1]['time_chunks'] == 5

    def test_main_displays_all_files(self, capsys):
        """Testa que main exibe todos os arquivos gerados"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=['repo1.json', 'repo2.json']), patch('coops.bronze.issues.extract_issues', return_value=['issues.json']), patch('coops.bronze.commits.extract_commits', return_value=['commits.json']), patch('coops.bronze.members.extract_members', return_value=['members.json']), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            bronze_extract.main()

        captured = capsys.readouterr()
        assert "Total files generated: 5" in captured.out
        assert "Repositories: 2" in captured.out
        assert "Issues/PRs: 1" in captured.out
        assert "Commits: 1" in captured.out
        assert "Members: 1" in captured.out

    def test_main_handles_extraction_error(self, capsys):
        """Testa tratamento de erro durante extração"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', side_effect=Exception("API Error")), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            with pytest.raises(SystemExit) as exc_info:
                bronze_extract.main()

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Bronze extraction failed" in captured.out
        assert "API Error" in captured.out

    def test_main_extracts_in_correct_order(self):
        """Testa que as extrações são feitas na ordem correta"""
        call_order = []

        def track_repos(*args, **kwargs):
            call_order.append('repos')
            return []

        def track_issues(*args, **kwargs):
            call_order.append('issues')
            return []

        def track_commits(*args, **kwargs):
            call_order.append('commits')
            return []

        def track_members(*args, **kwargs):
            call_order.append('members')
            return []

        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', side_effect=track_repos), patch('coops.bronze.issues.extract_issues', side_effect=track_issues), patch('coops.bronze.commits.extract_commits', side_effect=track_commits), patch('coops.bronze.members.extract_members', side_effect=track_members), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            bronze_extract.main()

        assert call_order == ['repos', 'issues', 'commits', 'members']

    def test_main_displays_timestamp(self, capsys):
        """Testa que main exibe timestamp de início"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
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

    def test_main_initializes_github_client(self, capsys, monkeypatch):
        """Testa que main inicializa o GitHubAPIClient com o token vindo de Settings"""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "my-secret-token")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_client_cls.call_args[0][0] == 'my-secret-token'

        # Verifica que o processo foi concluído sem erro
        captured = capsys.readouterr()
        assert "Bronze extraction completed" in captured.out

    def test_main_creates_passes_and_saves_watermark_store(self, monkeypatch):
        """main loads a WatermarkStore, threads it into the extractors, and saves it."""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]) as mock_issues, patch('coops.bronze.commits.extract_commits', return_value=[]) as mock_commits, patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]) as mock_structure, patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls, patch('coops.etl.bronze_extract.WatermarkStore') as mock_store_cls:
            store = mock_store_cls.return_value
            # main só grava o watermark numa execução
            # online; sem isso o mock teria offline
            # "verdadeiro" por acidente.
            mock_client_cls.return_value.offline = False
            from coops.etl import bronze_extract

            bronze_extract.main()

        mock_store_cls.assert_called_once()
        store.save.assert_called_once()
        assert mock_issues.call_args[1]['watermarks'] is store
        assert mock_commits.call_args[1]['watermarks'] is store
        assert mock_structure.call_args[1]['watermarks'] is store
        get_settings.cache_clear()

    def test_main_with_repo_flag(self):
        """--repo é repetível e chega ao extract_repositories como repo_filter"""
        with patch('sys.argv', ['bronze_extract.py', '--repo', 'coops-org/one', '--repo', 'coops-org/two']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_repos.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_repos.call_args[1]['repo_filter'] == ['coops-org/one', 'coops-org/two']

    def test_main_without_repo_defaults_to_none(self):
        """Sem --repo, repo_filter é None (sem seleção)"""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            mock_repos.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_repos.call_args[1]['repo_filter'] is None

    def test_main_offline_flag(self):
        """--offline chega ao cliente e implica uso do cache em todos os extratores"""
        with patch('sys.argv', ['bronze_extract.py', '--offline']), patch('coops.bronze.repositories.extract_repositories') as mock_repos, patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            mock_repos.return_value = []

            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_client_cls.call_args[1]['offline'] is True
            # Offline implies reading the cache, even
            # without an explicit --cache.
            assert mock_repos.call_args[1]['use_cache'] is True

    def test_main_cache_dir_flag(self):
        """--cache-dir chega ao construtor do cliente (o padrão é relativo ao cwd)"""
        with patch('sys.argv', ['bronze_extract.py', '--cache-dir', 'custom-cache']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_client_cls.call_args[1]['cache_dir'] == 'custom-cache'

    def test_main_cache_dir_defaults_to_cache(self):
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert mock_client_cls.call_args[1]['cache_dir'] == 'cache'

    # ---------------------------------------------------------------
    # Reconciliation wiring (#216): main() passes the bronze directory
    # and the mode — and NOTHING else. The narrowing decision is the
    # FILE's (repositories_filtered.json carries its own completeness
    # provenance), never argv's, because the narrowed run and the
    # reconciliation need not be the same process. The assertions are on
    # the CALL, never on printed output.
    # ---------------------------------------------------------------

    def test_main_reports_without_deleting_by_default(self, _isolated_settings):
        """A full run REPORTS the orphans; it does not remove them.

        The scheduled run surfacing the orphans is the fix; deleting them
        without anyone asking is a separate decision, and the flag is where
        it gets made (#244 review)."""
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            mock_client_cls.return_value.offline = False
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
    def test_main_passes_no_narrowing_to_the_reconciliation(self, _isolated_settings, argv):
        """--repo, --max-repos and --offline narrow the listing, and none of
        them reaches the reconciliation as an argument. An argv guard is a
        guard that is not there when it matters: run A caps and exits; run
        B reconciles with a clean argv and would delete every unlisted
        repository's files. The refusal must come from the listing's own
        provenance (tested in test_bronze_reconcile.py), so the call here
        is byte-for-byte the full run's call."""
        with patch('sys.argv', ['bronze_extract.py', *argv]), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient'):
            from coops.etl import bronze_extract

            bronze_extract.main()

            _isolated_settings.assert_called_once_with(
                "data/bronze", apply=False,
            )

    def test_main_deletes_nothing_without_the_apply_flag(self, _isolated_settings):
        """THE DEFAULT RUN DELETES NOTHING.

        A routine that removes files must not remove them because nobody
        passed a flag: the mode you get by forgetting has to be the safe
        one. Reviewed onto #244 after the first implementation shipped
        ``apply=not --reconcile-dry-run``, which deleted by default and
        which every library-level test passed, because they called
        ``reconcile_orphans`` directly and never went through ``main``.
        """
        with patch('sys.argv', ['bronze_extract.py']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            mock_client_cls.return_value.offline = False
            from coops.etl import bronze_extract

            bronze_extract.main()

            assert _isolated_settings.call_args[1]["apply"] is False

    def test_main_reconcile_apply_flag_opts_in(self, _isolated_settings):
        """--reconcile-apply is the only way deletion happens."""
        with patch('sys.argv', ['bronze_extract.py', '--reconcile-apply']), patch('coops.bronze.repositories.extract_repositories', return_value=[]), patch('coops.bronze.issues.extract_issues', return_value=[]), patch('coops.bronze.commits.extract_commits', return_value=[]), patch('coops.bronze.members.extract_members', return_value=[]), patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), patch('coops.etl.bronze_extract.update_data_registry'), patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
            mock_client_cls.return_value.offline = False
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

    def test_main_reports_and_publishes_the_dedupe(self, tmp_path, capsys):
        """main() prints the dedupe section and writes
        data/bronze/dedupe.json naming the deduped id — the published
        metadata half of #248's output requirement."""
        from coops.etl import bronze_extract

        self._bronze(tmp_path)

        with patch('sys.argv', ['bronze_extract.py']), \
             patch('coops.bronze.repositories.extract_repositories', return_value=[]), \
             patch('coops.bronze.issues.extract_issues', return_value=[]), \
             patch('coops.bronze.commits.extract_commits', return_value=[]), \
             patch('coops.bronze.members.extract_members', return_value=[]), \
             patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), \
             patch('coops.etl.bronze_extract.update_data_registry'), \
             patch('coops.etl.bronze_extract.GitHubAPIClient'):
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

    def test_main_publishes_the_refusal_not_just_the_dedupe(self, tmp_path, capsys):
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

        with patch('sys.argv', ['bronze_extract.py']), \
             patch('coops.bronze.repositories.extract_repositories', return_value=[]), \
             patch('coops.bronze.issues.extract_issues', return_value=[]), \
             patch('coops.bronze.commits.extract_commits', return_value=[]), \
             patch('coops.bronze.members.extract_members', return_value=[]), \
             patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]), \
             patch('coops.etl.bronze_extract.update_data_registry'), \
             patch('coops.etl.bronze_extract.GitHubAPIClient'):
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
