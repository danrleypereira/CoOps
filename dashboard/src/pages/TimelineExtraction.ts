import { fetchData, filterMetadata } from '../services/dataSource';

export interface TimelineData {
  date: string;
  users: {
    name?: string;
    repositories?: string[];
    activities: {
        commits: number;
        issues_created: number;
        issues_closed: number;
        prs_created: number;
        prs_closed: number;
        comments: number;
    }
  }[];
}

export class TimelineExtraction {

   
    static async extractTimelineData(time_filter: string, repo_filter?: string): Promise<TimelineData[]> {

        let path: string;

        if (time_filter === 'last_7_days') {
            path = 'gold/timeline_last_7_days.json';
        } else if (time_filter === 'last_12_months') {
            path = 'gold/timeline_last_12_months.json';
        } else {
            throw new Error(`Invalid time filter: ${time_filter}. Use 'last_7_days' or 'last_12_months'`);
        }

        const rawData = await fetchData<any[]>(path);
        const processedData = this.processTimelineData(rawData, repo_filter);

        return processedData;
    }
    
    static processTimelineData(rawData: any[], repo_filter?: string): TimelineData[] {
        // Filter out metadata entry and map directly to TimelineData
        const timelineData: TimelineData[] = rawData
            .filter((item: any) => item._metadata === undefined)
            .map((item: any) => ({
                date: item.date,
                users: item.authors
                    .map((author: any) => ({
                        name: author.name,
                        repositories: author.repositories || [],
                        activities: {
                            commits: author.commits || 0,
                            issues_created: author.issues_created || 0,
                            issues_closed: author.issues_closed || 0,
                            prs_created: author.prs_created || 0,
                            prs_closed: author.prs_closed || 0,
                            comments: author.comments || 0
                        }
                    }))
                    // Apply repo filter per user if provided
                    .filter((user: any) => {
                        if (!repo_filter || repo_filter === 'all') return true;
                        return user.repositories && user.repositories.some((repo: string) => 
                            repo.toLowerCase().includes(repo_filter.toLowerCase())
                        );
                    })
            }));
            // Do not remove empty days - keep all days even without users

        return timelineData;
    }

}