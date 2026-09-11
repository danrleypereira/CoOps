#!/usr/bin/env python3

import argparse
import sys
from datetime import datetime

from coops.utils.github_api import update_data_registry

def main():
    argparse.ArgumentParser(description='Process Silver data to Gold layer').parse_args()

    print(f"Starting Gold layer processing")
    print(f"Started at: {datetime.now().isoformat()}")
    
    try:
        # Import individual processors
        from coops.gold.timeline_aggregation import process_timeline_aggregation
        
        # Process data
        print("\nProcessing timeline aggregations...")
        timeline_files = process_timeline_aggregation()

        # Update registry
        all_files = timeline_files
        update_data_registry('gold', 'all_processed', all_files)
        
        print(f"\nGold processing completed successfully!")
        print(f"Generated {len(all_files)} files:")
        for file_path in all_files:
            print(f"   - {file_path}")
            
    except Exception as e:
        print(f"\n Error during gold processing: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
