
import argparse
import sys
from datetime import datetime

from coops.utils.github_api import update_data_registry


def main():
    argparse.ArgumentParser(description='Process Silver data to Gold layer').parse_args()

    print("Starting Gold layer processing")
    print(f"Started at: {datetime.now().isoformat()}")  # noqa: DTZ005 — human log, not data: #143 deliberately left console timestamps in the operator's local wall clock
    
    try:
        # Import individual processors
        from coops.gold.timeline_aggregation import process_timeline_aggregation
        
        # Process data
        print("\nProcessing timeline aggregations...")
        timeline_files = process_timeline_aggregation()

        # Update registry
        all_files = timeline_files
        update_data_registry('gold', 'all_processed', all_files)
        
        print("\nGold processing completed successfully!")
        print(f"Generated {len(all_files)} files:")
        for file_path in all_files:
            print(f"   - {file_path}")
            
    except Exception as e:  # noqa: BLE001 — CLI boundary: report the failure and exit non-zero
        print(f"\n Error during gold processing: {e!s}")
        sys.exit(1)

if __name__ == "__main__":
    main()
