#!/usr/bin/env python3
import json
import os
from datetime import datetime

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

# Generate executive dashboard KPIs
members_analytics = load_json('data/silver/members_analytics.json') or []
contribution_metrics = load_json('data/silver/contribution_metrics.json') or []
network_stats = load_json('data/silver/network_statistics.json') or {}
temporal_stats = load_json('data/silver/temporal_statistics.json') or {}

# Skip metadata if present
if isinstance(members_analytics, list) and len(members_analytics) > 0 and '_metadata' in members_analytics[0]:
    members_analytics = members_analytics[1:]
if isinstance(contribution_metrics, list) and len(contribution_metrics) > 0 and '_metadata' in contribution_metrics[0]:
    contribution_metrics = contribution_metrics[1:]

executive_kpis = {
    'generated_at': datetime.now().isoformat(),
    'organization_health': {
        'total_members': len(members_analytics),
        'active_contributors': len([c for c in contribution_metrics if c.get('has_contributed', False)]),
        'new_members': len([m for m in members_analytics if m.get('status') == 'new']),
        'established_members': len([m for m in members_analytics if m.get('status') == 'established'])
    },
    'collaboration_metrics': {
        'total_collaborations': network_stats.get('total_collaborations', 0),
        'cross_repo_contributors': network_stats.get('cross_repo_contributors', 0),
        'avg_collaborators_per_user': network_stats.get('avg_collaborators_per_user', 0)
    },
    'activity_metrics': {
        'total_events': temporal_stats.get('total_events', 0),
        'avg_daily_activity': temporal_stats.get('avg_daily_activity', 0),
        'date_range_days': temporal_stats.get('date_range', {}).get('days', 0)
    },
    'top_contributors': sorted(contribution_metrics, key=lambda x: x.get('total_contributions', 0), reverse=True)[:10]
}

save_json(executive_kpis, 'data/gold/executive_dashboard.json')

# Generate member performance tiers
if contribution_metrics:
    contrib_values = [c['total_contributions'] for c in contribution_metrics if c.get('has_contributed')]
    if contrib_values:
        contrib_values.sort(reverse=True)
        top_10_threshold = contrib_values[min(len(contrib_values) - 1, int(len(contrib_values) * 0.1))]
        top_25_threshold = contrib_values[min(len(contrib_values) - 1, int(len(contrib_values) * 0.25))]
        
        performance_tiers = {
            'top_performers': [c for c in contribution_metrics if c['total_contributions'] >= top_10_threshold],
            'regular_contributors': [c for c in contribution_metrics if top_25_threshold <= c['total_contributions'] < top_10_threshold],
            'occasional_contributors': [c for c in contribution_metrics if 0 < c['total_contributions'] < top_25_threshold],
            'non_contributors': [c for c in contribution_metrics if c['total_contributions'] == 0]
        }
        
        save_json(performance_tiers, 'data/gold/performance_tiers.json')

print("✅ Gold layer aggregation completed")
