"""
Main orchestrator for Silver layer data processing
Transforms bronze raw data into analytics-ready formats
"""

import argparse
import sys
from datetime import datetime

from coops.utils.github_api import update_data_registry


def main():
    argparse.ArgumentParser(description='Process Bronze data to Silver layer').parse_args()

    print("Starting Silver layer processing")
    print(f"Started at: {datetime.now().isoformat()}")  # noqa: DTZ005 — human log, not data: #143 deliberately left console timestamps in the operator's local wall clock

    try:
        # Import and run individual processors
        from coops.silver.available_repos import process_available_repos
        from coops.silver.collaboration_networks import process_collaboration_networks
        from coops.silver.contribution_metrics import process_contribution_metrics
        from coops.silver.file_language_analysis import process_file_language_analysis
        from coops.silver.member_analytics import process_member_analytics
        from coops.silver.members_statistics import process_members_statistics
        from coops.silver.temporal_analysis import process_temporal_analysis

        # Process data in logical order
        print("\nListing available repositories...")
        repo_list_files = process_available_repos()

        print("\nStep 1: Processing member analytics...")
        member_files = process_member_analytics()

        print("\nStep 2: Processing contribution metrics...")
        contrib_files = process_contribution_metrics()

        print("\nStep 3: Processing collaboration networks...")
        collab_files = process_collaboration_networks()

        print("\nStep 4: Processing temporal analysis...")
        temporal_files = process_temporal_analysis()

        print("\nStep 5: Processing members statistics...")
        members_stats_files = process_members_statistics()

        print("\nStep 6: Processing language analysis...")
        language_files = process_file_language_analysis(
            max_sample_files=10,
            sample_strategy='largest',
            save_hierarchy=True
        )

        # Update registry
        all_files = (member_files + contrib_files + collab_files + temporal_files
                     + members_stats_files + language_files + repo_list_files)
        update_data_registry('silver', 'all_processed', all_files)

        print("\nSilver processing completed successfully!")
        print(f"Generated {len(all_files)} files:")
        for file_path in all_files:
            print(f"   - {file_path}")

    except Exception as e:  # noqa: BLE001 — CLI boundary: report the failure and exit non-zero
        print(f"\nError during silver processing: {e!s}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
