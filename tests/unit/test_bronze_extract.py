"""
Testes unitários para o módulo bronze_extract.

Testa a orquestração da extração da camada Bronze.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys

from pydantic import ValidationError


class TestBronzeExtract:
    """Testes para o script bronze_extract"""

    @pytest.fixture(autouse=True)
    def _isolated_settings(self, monkeypatch):
        """github_token/github_org agora vêm de coops.infrastructure.get_settings()
        (lru_cache'd process-wide), então cada teste define o env necessário e
        limpa o cache antes/depois pra não vazar entre testes."""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_ORG", "coops-org")
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_main_extracts_all_layers(self, capsys):
        """Testa que main extrai todas as camadas Bronze"""
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=['repo.json']):
                with patch('coops.bronze.issues.extract_issues', return_value=['issues.json']):
                    with patch('coops.bronze.commits.extract_commits', return_value=['commits.json']):
                        with patch('coops.bronze.members.extract_members', return_value=['members.json']):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
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
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits', return_value=[]):
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

        captured = capsys.readouterr()
        assert "organization: my-org" in captured.out


    def test_main_with_cache_flag(self):
        """Testa que main passa o flag --cache para os extractors"""
        with patch('sys.argv', ['bronze_extract.py', '--cache']):
            with patch('coops.bronze.repositories.extract_repositories') as mock_repos:
                with patch('coops.bronze.issues.extract_issues') as mock_issues:
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members') as mock_members:
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
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
        with patch('sys.argv', ['bronze_extract.py', '--commits-method', 'graphql']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['method'] == 'graphql'

    def test_main_with_time_range(self):
        """Testa que main aceita argumentos --since e --until"""
        with patch('sys.argv', ['bronze_extract.py',
                                '--since', '2024-01-01T00:00:00Z',
                                '--until', '2024-12-31T23:59:59Z']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['since'] == '2024-01-01T00:00:00Z'
                                        assert mock_commits.call_args[1]['until'] == '2024-12-31T23:59:59Z'

    def test_main_with_max_commits_per_repo(self):
        """Testa que main aceita --max-commits-per-repo"""
        with patch('sys.argv', ['bronze_extract.py', '--max-commits-per-repo', '1000']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['max_commits_per_repo'] == 1000

    def test_main_with_max_issues_and_max_prs(self):
        """Testa que main aceita --max-issues e --max-prs e repassa pra extract_issues"""
        with patch('sys.argv', ['bronze_extract.py', '--max-issues', '5', '--max-prs', '3']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues') as mock_issues:
                    with patch('coops.bronze.commits.extract_commits', return_value=[]):
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_issues.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_issues.call_args[1]['max_issues'] == 5
                                        assert mock_issues.call_args[1]['max_prs'] == 3

    def test_main_without_max_issues_and_max_prs_defaults_to_none(self):
        """Testa que --max-issues/--max-prs são None quando não passados (sem cap)"""
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues') as mock_issues:
                    with patch('coops.bronze.commits.extract_commits', return_value=[]):
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_issues.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_issues.call_args[1]['max_issues'] is None
                                        assert mock_issues.call_args[1]['max_prs'] is None

    def test_main_with_active_branches(self):
        """Testa que main aceita --include-active-branches e --active-days"""
        with patch('sys.argv', ['bronze_extract.py',
                                '--include-active-branches', '--active-days', '60']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['include_active_branches'] is True
                                        assert mock_commits.call_args[1]['active_days'] == 60

    def test_main_with_custom_page_size(self):
        """Testa que main aceita --commits-page-size"""
        with patch('sys.argv', ['bronze_extract.py', '--commits-page-size', '100']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['page_size'] == 100

    def test_main_with_time_chunks(self):
        """Testa que main aceita --time-chunks"""
        with patch('sys.argv', ['bronze_extract.py', '--time-chunks', '5']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits') as mock_commits:
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        mock_commits.return_value = []

                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_commits.call_args[1]['time_chunks'] == 5

    def test_main_displays_all_files(self, capsys):
        """Testa que main exibe todos os arquivos gerados"""
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=['repo1.json', 'repo2.json']):
                with patch('coops.bronze.issues.extract_issues', return_value=['issues.json']):
                    with patch('coops.bronze.commits.extract_commits', return_value=['commits.json']):
                        with patch('coops.bronze.members.extract_members', return_value=['members.json']):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
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
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', side_effect=Exception("API Error")):
                with patch('coops.etl.bronze_extract.GitHubAPIClient'):
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

        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', side_effect=track_repos):
                with patch('coops.bronze.issues.extract_issues', side_effect=track_issues):
                    with patch('coops.bronze.commits.extract_commits', side_effect=track_commits):
                        with patch('coops.bronze.members.extract_members', side_effect=track_members):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

        assert call_order == ['repos', 'issues', 'commits', 'members']

    def test_main_displays_timestamp(self, capsys):
        """Testa que main exibe timestamp de início"""
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits', return_value=[]):
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient'):
                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

        captured = capsys.readouterr()
        assert "Started at:" in captured.out

    def test_main_requires_github_token_and_org(self, monkeypatch, tmp_path):
        """Testa que main requer GITHUB_TOKEN/GITHUB_ORG (via Settings, não mais --token/--org).
        Precisa isolar o cwd: um .secrets real na raiz do repo (com credenciais de
        verdade ou placeholders) seria lido pelo Settings() mesmo com os env vars
        removidos, mascarando a falta de configuração."""
        from coops.infrastructure.config import get_settings
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ORG", raising=False)
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']):
            from coops.etl import bronze_extract

            with pytest.raises(ValidationError):
                bronze_extract.main()

    def test_main_initializes_github_client(self, capsys, monkeypatch):
        """Testa que main inicializa o GitHubAPIClient com o token vindo de Settings"""
        from coops.infrastructure.config import get_settings
        monkeypatch.setenv("GITHUB_TOKEN", "my-secret-token")
        get_settings.cache_clear()
        with patch('sys.argv', ['bronze_extract.py']):
            with patch('coops.bronze.repositories.extract_repositories', return_value=[]):
                with patch('coops.bronze.issues.extract_issues', return_value=[]):
                    with patch('coops.bronze.commits.extract_commits', return_value=[]):
                        with patch('coops.bronze.members.extract_members', return_value=[]):
                            with patch('coops.bronze.repository_structure.extract_repository_structure', return_value=[]):
                                with patch('coops.etl.bronze_extract.update_data_registry'):
                                    with patch('coops.etl.bronze_extract.GitHubAPIClient') as mock_client_cls:
                                        from coops.etl import bronze_extract

                                        bronze_extract.main()

                                        assert mock_client_cls.call_args[0][0] == 'my-secret-token'

        # Verifica que o processo foi concluído sem erro
        captured = capsys.readouterr()
        assert "Bronze extraction completed" in captured.out
