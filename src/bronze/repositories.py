#!/usr/bin/env python3
"""
Repository extraction for Bronze layer
Extracts raw repository data from GitHub API
"""

import os
from typing import List
from utils.github_api import GitHubAPIClient, OrganizationConfig, save_json_data

def extract_repositories(client: GitHubAPIClient, config: OrganizationConfig, use_cache: bool = True) -> List[str]:
    """Extract organization repositories to bronze layer"""
    
    # Get organization repositories
    repos_url = f"https://api.github.com/orgs/{config.org_name}/repos"
    raw_repos = client.get_with_cache(repos_url, use_cache)
    
    if not raw_repos:
        print("❌ Failed to fetch repositories")
        return []
    
    # Filter out blacklisted repos
    filtered_repos = []
    for repo in raw_repos:
        if not config.should_skip_repo(repo):
            filtered_repos.append(repo)
        else:
            print(f"⏭️  Skipping repository: {repo.get('name', 'unknown')} (blacklisted/fork)")
    
    print(f"📊 Found {len(filtered_repos)} repositories (filtered from {len(raw_repos)})")
    
    generated_files = []
    
    # Save all repositories
    repos_file = save_json_data(
        raw_repos, 
        "data/bronze/repositories_raw.json"
    )
    generated_files.append(repos_file)
    
    # Save filtered repositories
    filtered_file = save_json_data(
        filtered_repos,
        "data/bronze/repositories_filtered.json"
    )
    generated_files.append(filtered_file)
    
    # Save individual repository details
    repo_details = []
    for repo in filtered_repos[:5]:  # Limit to first 5 for detailed extraction
        repo_detail_url = f"https://api.github.com/repos/{repo['full_name']}"
        detail = client.get_with_cache(repo_detail_url, use_cache)
        if detail:
            repo_details.append(detail)
            
            # Save individual repo file
            repo_file = save_json_data(
                detail,
                f"data/bronze/repo_{repo['name']}.json"
            )
            generated_files.append(repo_file)
    
    if repo_details:
        details_file = save_json_data(
            repo_details,
            "data/bronze/repositories_detailed.json"
        )
        generated_files.append(details_file)
    
    return generated_files