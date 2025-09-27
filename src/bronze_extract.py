#!/usr/bin/env python3
"""
Main orchestrator for Bronze layer data extraction
Extracts raw data from GitHub API and saves to bronze layer
"""

import argparse
import sys
import os
from datetime import datetime

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.github_api import GitHubAPIClient, OrganizationConfig, update_data_registry

def main():
    parser = argparse.ArgumentParser(description='Extract GitHub organization data to Bronze layer')
    parser.add_argument('--token', required=True, help='GitHub Personal Access Token')
    parser.add_argument('--org', default='coops-org', help='GitHub organization name')
    parser.add_argument('--cache', action='store_true', help='Use cached data when available')
    
    args = parser.parse_args()
    
    print(f"🔄 Starting Bronze layer extraction for organization: {args.org}")
    print(f"📅 Started at: {datetime.now().isoformat()}")
    
    # Initialize API client and configuration
    client = GitHubAPIClient(args.token)
    config = OrganizationConfig(args.org)
    
    try:
        # Import and run individual extractors
        from bronze.repositories import extract_repositories
        from bronze.members import extract_members
        from bronze.issues import extract_issues
        from bronze.commits import extract_commits
        
        # Extract data in dependency order
        print("\n📊 Step 1: Extracting repositories...")
        repo_files = extract_repositories(client, config, use_cache=args.cache)
        
        print("\n👥 Step 2: Extracting organization members...")
        member_files = extract_members(client, config, use_cache=args.cache)
        
        print("\n🐛 Step 3: Extracting issues and pull requests...")
        issue_files = extract_issues(client, config, use_cache=args.cache)
        
        print("\n💾 Step 4: Extracting commits...")
        commit_files = extract_commits(client, config, use_cache=args.cache)
        
        # Update registry
        all_files = repo_files + member_files + issue_files + commit_files
        update_data_registry('bronze', 'all_extractions', all_files)
        
        print(f"\n✅ Bronze extraction completed successfully!")
        print(f"📁 Generated {len(all_files)} files:")
        for file_path in all_files:
            print(f"   - {file_path}")
            
    except Exception as e:
        print(f"\n❌ Error during bronze extraction: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()