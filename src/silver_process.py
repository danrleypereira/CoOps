#!/usr/bin/env python3
"""
Main orchestrator for Silver layer data processing
Transforms bronze raw data into analytics-ready formats
"""

import argparse
import sys
import os
from datetime import datetime

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.github_api import update_data_registry

def main():
    parser = argparse.ArgumentParser(description='Process Bronze data to Silver layer')
    parser.add_argument('--org', default='coops-org', help='GitHub organization name')
    
    args = parser.parse_args()
    
    print(f"🔄 Starting Silver layer processing")
    print(f"📅 Started at: {datetime.now().isoformat()}")
    
    try:
        # Import and run individual processors
        from silver.member_analytics import process_member_analytics
        from silver.contribution_metrics import process_contribution_metrics
        from silver.collaboration_networks import process_collaboration_networks
        from silver.temporal_analysis import process_temporal_analysis
        
        # Process data in logical order
        print("\n👥 Step 1: Processing member analytics...")
        member_files = process_member_analytics()
        
        print("\n📊 Step 2: Processing contribution metrics...")
        contrib_files = process_contribution_metrics()
        
        print("\n🤝 Step 3: Processing collaboration networks...")
        collab_files = process_collaboration_networks()
        
        print("\n📅 Step 4: Processing temporal analysis...")
        temporal_files = process_temporal_analysis()
        
        # Update registry
        all_files = member_files + contrib_files + collab_files + temporal_files
        update_data_registry('silver', 'all_processed', all_files)
        
        print(f"\n✅ Silver processing completed successfully!")
        print(f"📁 Generated {len(all_files)} files:")
        for file_path in all_files:
            print(f"   - {file_path}")
            
    except Exception as e:
        print(f"\n❌ Error during silver processing: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()