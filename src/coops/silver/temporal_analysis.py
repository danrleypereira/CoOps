#!/usr/bin/env python3
"""
Temporal analysis processing for Silver layer
Analyzes time-based patterns and trends
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any
from coops.utils.github_api import save_json_data, parse_github_date
from coops.silver.members_statistics import display_name, observe_spelling
from coops.silver.bronze_input import load_family

def process_temporal_analysis() -> List[str]:
    """Process temporal data for time-based analytics"""

    # Load bronze data: per-repository files, not the _all aggregates
    # (redundant concatenations of exactly these records — issue #170).
    issues_data = load_family("issues")
    prs_data = load_family("prs")
    commits_data = load_family("commits")
    issue_events_data = load_family("issue_events")

    generated_files = []

    # Observed spellings of each identity's real name (issue #151, step 3).
    # Events keep carrying the raw identity in `user` — that is the join key
    # Gold uses — so the display label is derived here, once at aggregation,
    # from everything observed, instead of being written per event. The
    # accumulation mirrors `members_statistics` over the same bronze
    # records, so both files render the same label for the same identity.
    name_counts = defaultdict(lambda: defaultdict(int))

    # Collect all time-based events
    all_events = []

    # Process issues - Squad improvement: more robust user identifier extraction
    for issue in issues_data:
        created_at = parse_github_date(issue.get('created_at'))
        if created_at:
            # Use login as primary identifier (unique on GitHub)
            user = issue.get('user') or {}
            user_identifier = user.get('login') or user.get('name') or 'unknown'
            observe_spelling(name_counts[user_identifier], user.get('name'))

            all_events.append({
                'date': created_at,
                'type': 'issue_created',
                'repo': issue.get('repo_name', 'unknown'),
                'user': user_identifier
            })

        updated_at = parse_github_date(issue.get('updated_at'))
        if updated_at and issue.get('state') == 'closed':
            user = issue.get('user') or {}
            user_identifier = user.get('login') or user.get('name') or 'unknown'

            all_events.append({
                'date': updated_at,
                'type': 'issue_closed',
                'repo': issue.get('repo_name', 'unknown'),
                'user': user_identifier
            })

    # Process PRs - Squad improvement: more robust user identifier extraction
    for pr in prs_data:
        created_at = parse_github_date(pr.get('created_at'))
        if created_at:
            # Use login as primary identifier (unique on GitHub)
            user = pr.get('user') or {}
            user_identifier = user.get('login') or user.get('name') or 'unknown'
            observe_spelling(name_counts[user_identifier], user.get('name'))

            all_events.append({
                'date': created_at,
                'type': 'pr_created',
                'repo': pr.get('repo_name', 'unknown'),
                'user': user_identifier
            })

        updated_at = parse_github_date(pr.get('updated_at'))
        if updated_at and pr.get('state') == 'closed':
            user = pr.get('user') or {}
            user_identifier = user.get('login') or user.get('name') or 'unknown'

            all_events.append({
                'date': updated_at,
                'type': 'pr_closed',
                'repo': pr.get('repo_name', 'unknown'),
                'user': user_identifier
            })

    # Process commits - Squad improvement: multi-level author extraction with additions/deletions
    for commit in commits_data:
        commit_date = None
        commit_obj = commit.get('commit') or {}
        author_obj = commit_obj.get('author') or {}
        if author_obj.get('date'):
            commit_date = parse_github_date(author_obj['date'])

        if commit_date:
            # Try to get user identifier from multiple possible locations
            # Priority: login (unique GitHub ID) > name (can vary per commit config)
            user_identifier = 'unknown'

            # First try: commit.commit.author.login (from GraphQL or enriched REST)
            if author_obj.get('login'):
                user_identifier = author_obj['login']
            # Second try: commit.author.login (from REST API root level)
            elif commit.get('author', {}) and commit['author'].get('login'):
                user_identifier = commit['author']['login']
            # Third try: author_email_hash (stable identity for unlinked authors)
            elif author_obj.get('author_email_hash'):
                user_identifier = author_obj['author_email_hash']
            # Fourth try: commit.commit.author.name (fallback, less reliable)
            elif author_obj.get('name'):
                user_identifier = author_obj['name']

            # The chain above ranks the *identity* (`id`): a key must be
            # unique and stable, so the stable hash outranks the
            # self-reported name here. The *display label* ranks the other
            # way around — login > real name > hash prefix — because a label
            # must be legible; it is applied at the daily summary via
            # display_name, never per event (issue #151, step 3).
            observe_spelling(name_counts[user_identifier], author_obj.get('name'))

            all_events.append({
                'date': commit_date,
                'type': 'commit',
                'repo': commit.get('repo_name', 'unknown'),
                'user': user_identifier,
                'additions': commit.get('additions'),
                'deletions': commit.get('deletions'),
                'total_changes': commit.get('total_changes')
            })

    # Process issue events - Squad improvement: more robust actor extraction
    for event in issue_events_data:
        event_date = parse_github_date(event.get('created_at'))
        if event_date:
            # Use login as primary identifier (unique on GitHub)
            actor = event.get('actor') or {}
            user_identifier = actor.get('login') or actor.get('name') or 'unknown'
            observe_spelling(name_counts[user_identifier], actor.get('name'))

            all_events.append({
                'date': event_date,
                'type': f"event_{event.get('event', 'unknown')}",
                'repo': event.get('repo_name', 'unknown'),
                'user': user_identifier
            })

    # Sort events by date
    all_events.sort(key=lambda x: x['date'])

    # Save all temporal events
    events_file = save_json_data(
        [{**event, 'date': event['date'].isoformat()} for event in all_events],
        "data/silver/temporal_events.json"
    )
    generated_files.append(events_file)

    # Create daily activity summary - Squad improvement: per-author breakdown
    daily_activity = defaultdict(lambda: {
        'date': None,
        'total_events': 0,
        'issues_created': 0,
        'issues_closed': 0,
        'prs_created': 0,
        'prs_closed': 0,
        'commits': 0,
        'comments': 0,
        'unique_users': set(),
        'unique_repos': set(),
        'authors': defaultdict(lambda: {
            'commits': 0,
            'issues_created': 0,
            'issues_closed': 0,
            'prs_created': 0,
            'prs_closed': 0,
            'comments': 0
        })
    })

    for event in all_events:
        date_key = event['date'].date().isoformat()
        day_data = daily_activity[date_key]

        day_data['date'] = date_key
        day_data['total_events'] += 1
        day_data['unique_users'].add(event['user'])
        day_data['unique_repos'].add(event['repo'])

        author_id = event['user']

        if event['type'] == 'issue_created':
            day_data['issues_created'] += 1
            day_data['authors'][author_id]['issues_created'] += 1
        elif event['type'] == 'issue_closed':
            day_data['issues_closed'] += 1
            day_data['authors'][author_id]['issues_closed'] += 1
        elif event['type'] == 'pr_created':
            day_data['prs_created'] += 1
            day_data['authors'][author_id]['prs_created'] += 1
        elif event['type'] == 'pr_closed':
            day_data['prs_closed'] += 1
            day_data['authors'][author_id]['prs_closed'] += 1
        elif event['type'] == 'commit':
            day_data['commits'] += 1
            day_data['authors'][author_id]['commits'] += 1
        elif 'comment' in event['type']:
            day_data['comments'] += 1
            day_data['authors'][author_id]['comments'] += 1

    # Convert sets to counts and prepare for JSON serialization
    daily_summary = []
    for date_key, data in sorted(daily_activity.items()):
        data['unique_users'] = len(data['unique_users'])
        data['unique_repos'] = len(data['unique_repos'])

        # Convert authors dict to list for JSON serialization. `id` keeps
        # the raw identity; `name` is the same display label
        # members_statistics renders (login -> real name ->
        # "Unknown contributor (<hash8>)"), decided here at aggregation from
        # every spelling observed — the two files are read side by side and
        # must agree on the label for the same identity.
        authors_list = []
        for author_id, stats in data['authors'].items():
            authors_list.append({
                'id': author_id,
                'name': display_name(author_id, name_counts.get(author_id)),
                'commits': stats['commits'],
                'issues_created': stats['issues_created'],
                'issues_closed': stats['issues_closed'],
                'prs_created': stats['prs_created'],
                'prs_closed': stats['prs_closed'],
                'comments': stats['comments']
            })
        data['authors'] = authors_list

        daily_summary.append(data)

    daily_file = save_json_data(
        daily_summary,
        "data/silver/daily_activity_summary.json"
    )
    generated_files.append(daily_file)

    # Create weekly activity heatmap data
    weekly_heatmap = defaultdict(lambda: defaultdict(int))

    for event in all_events:
        day_of_week = event['date'].weekday()  # 0=Monday, 6=Sunday
        hour = event['date'].hour
        weekly_heatmap[day_of_week][hour] += 1

    # Convert to structured format
    heatmap_data = []
    for day in range(7):  # Monday to Sunday
        for hour in range(24):
            heatmap_data.append({
                'day_of_week': day,
                'hour': hour,
                'activity_count': weekly_heatmap[day][hour]
            })

    heatmap_file = save_json_data(
        heatmap_data,
        "data/silver/activity_heatmap.json"
    )
    generated_files.append(heatmap_file)

    # Calculate cycle times for issues and PRs
    cycle_times = []

    # Issues cycle time
    for issue in issues_data:
        if issue.get('state') == 'closed':
            created = parse_github_date(issue.get('created_at'))
            closed = parse_github_date(issue.get('closed_at', issue.get('updated_at')))

            if created and closed and closed > created:
                cycle_time_days = (closed - created).total_seconds() / (24 * 3600)
                cycle_times.append({
                    'type': 'issue',
                    'repo': issue.get('repo_name', 'unknown'),
                    'number': issue.get('number'),
                    'created_at': created.isoformat(),
                    'closed_at': closed.isoformat(),
                    'cycle_time_days': cycle_time_days
                })

    # PRs cycle time
    for pr in prs_data:
        if pr.get('state') == 'closed':
            created = parse_github_date(pr.get('created_at'))
            closed = parse_github_date(pr.get('closed_at', pr.get('updated_at')))

            if created and closed and closed > created:
                cycle_time_days = (closed - created).total_seconds() / (24 * 3600)
                cycle_times.append({
                    'type': 'pr',
                    'repo': pr.get('repo_name', 'unknown'),
                    'number': pr.get('number'),
                    'created_at': created.isoformat(),
                    'closed_at': closed.isoformat(),
                    'cycle_time_days': cycle_time_days
                })

    if cycle_times:
        cycle_times_file = save_json_data(
            cycle_times,
            "data/silver/cycle_times.json"
        )
        generated_files.append(cycle_times_file)

    # Create temporal summary statistics
    if all_events:
        min_date = min(event['date'] for event in all_events)
        max_date = max(event['date'] for event in all_events)

        temporal_stats = {
            'total_events': len(all_events),
            'date_range': {
                'start': min_date.isoformat(),
                'end': max_date.isoformat(),
                'days': (max_date - min_date).days
            },
            'events_by_type': {},
            'avg_daily_activity': len(all_events) / max(1, (max_date - min_date).days),
            'cycle_time_stats': {}
        }

        # Count events by type
        for event in all_events:
            event_type = event['type']
            temporal_stats['events_by_type'][event_type] = temporal_stats['events_by_type'].get(event_type, 0) + 1

        # Calculate cycle time statistics
        if cycle_times:
            cycle_time_values = [ct['cycle_time_days'] for ct in cycle_times]
            temporal_stats['cycle_time_stats'] = {
                'count': len(cycle_time_values),
                'avg_days': sum(cycle_time_values) / len(cycle_time_values),
                'median_days': sorted(cycle_time_values)[len(cycle_time_values) // 2],
                'min_days': min(cycle_time_values),
                'max_days': max(cycle_time_values)
            }

        stats_file = save_json_data(
            temporal_stats,
            "data/silver/temporal_statistics.json"
        )
        generated_files.append(stats_file)

    print(f"Processed temporal analysis: {len(all_events)} events, {len(daily_summary)} days")
    return generated_files
