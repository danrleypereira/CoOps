import { fetchData, isDataNotFoundError } from '../services/dataSource';

export interface LanguageAnalysisFile {
  path: string;
  name: string;
  size: number;
  extension: string;
}

export interface LanguageData {
  language: string;
  file_count: number;
  total_bytes: number;
  percentage: number;
  files?: LanguageAnalysisFile[];
  has_more?: boolean;
}

export interface LanguageAnalysis {
  repository: string;
  owner: string;
  branch: string;
  analyzed_at?: string;
  sample_config?: {
    max_files_per_language: number;
    strategy: string;
  };
  total_files: number;
  total_bytes: number;
  languages: LanguageData[];
}

/**
 * Node of the per-repository file tree written by the pipeline
 * (`convert_tree_to_hierarchy` in src/coops/silver/file_language_analysis.py).
 */
export interface RepoHierarchyNode {
  name: string;
  type: 'file' | 'directory';
  path?: string;
  language?: string;
  size?: number;
  extension?: string;
  children?: RepoHierarchyNode[];
}

/** Shape of `data/silver/hierarchy_<repo>.json`: metadata wrapping the tree root. */
export interface RepoHierarchyFile {
  repository: string;
  owner?: string;
  branch?: string;
  extracted_at?: string;
  hierarchy: RepoHierarchyNode;
}

export class VisualizationUtils {
  private static readonly DATA_PATH = 'silver/language_analysis_all.json';
  private static cache: Map<string, LanguageAnalysis> = new Map();
  private static cacheLoaded = false;

  /**
   * Load all language analysis data into cache
   */
  private static async loadAllLanguageData(): Promise<void> {
    if (this.cacheLoaded) return;

    try {
      const data = await fetchData<unknown>(this.DATA_PATH);

      // Filtra apenas objetos válidos (ignora a entrada de _metadata). Não usar
      // filterMetadata aqui: cada registro de análise também carrega sua
      // própria chave _metadata.
      const analyses: LanguageAnalysis[] = Array.isArray(data) 
        ? data.filter((item: any) => item.repository && item.languages)
        : [];

      // Popula o cache
      analyses.forEach((analysis) => {
        this.cache.set(analysis.repository, analysis);
      });

      this.cacheLoaded = true;
    } catch (error) {
      if (!isDataNotFoundError(error)) {
        console.error("Error loading language analysis data:", error);
      }
      throw error;
    }
  }

  /**
   * Fetch available repository names from cache
   */
  static async fetchAvailableRepos(): Promise<string[]> {
    try {
      await this.loadAllLanguageData();
      return Array.from(this.cache.keys());
    } catch (error) {
      console.error('Error fetching repositories:', error);
      return [];
    }
  }

  /**
   * Fetch language analysis data for a specific repository from cache
   * 
   * @param repoName - Name of the repository
   * @returns Language analysis data, or null if the repository isn't in the file
   * @throws DataNotFoundError when the analysis file hasn't been generated yet,
   *   or the original error for network/HTTP/parse failures
   */
  static async fetchLanguageData(repoName: string): Promise<LanguageAnalysis | null> {
    await this.loadAllLanguageData();
    const data = this.cache.get(repoName);
    if (!data) {
      console.warn(`Repository "${repoName}" not found in cache`);
      return null;
    }
    return data;
  }

  /**
   * Fetch the file tree (circle pack hierarchy) of a specific repository
   * from `silver/hierarchy_<repo>.json`.
   *
   * @param repoName - Name of the repository
   * @returns Root node of the tree (the file's `hierarchy` field), or null if
   *   the file hasn't been generated or has no tree
   * @throws the original error for network/HTTP/parse failures
   */
  static async fetchTreeData(repoName: string): Promise<RepoHierarchyNode | null> {
    let file: RepoHierarchyFile | null;
    try {
      file = await fetchData<RepoHierarchyFile | null>(
        `silver/hierarchy_${encodeURIComponent(repoName)}.json`
      );
    } catch (error) {
      if (isDataNotFoundError(error)) return null;
      console.error(`Error fetching tree data for ${repoName}:`, error);
      throw error;
    }
    const hierarchy = file && typeof file === 'object' ? file.hierarchy : null;
    return hierarchy && typeof hierarchy === 'object' ? hierarchy : null;
  }

  /**
   * Get color for a programming language
   */
  static getLanguageColor(language: string): string {
    const colors: { [key: string]: string } = {
      JavaScript: "#f1e05a",
      TypeScript: "#2b7489",
      Python: "#3572A5",
      Java: "#b07219",
      HTML: "#e34c26",
      CSS: "#563d7c",
      Ruby: "#701516",
      Go: "#00ADD8",
      Rust: "#dea584",
      PHP: "#4F5D95",
      C: "#555555",
      "C++": "#f34b7d",
      "C#": "#178600",
      Shell: "#89e051",
      Swift: "#ffac45",
      Kotlin: "#F18E33",
      Dart: "#00B4AB",
      Vue: "#41b883",
      Svelte: "#ff3e00",
    };

    return colors[language] || "#8e8e8e";
  }

  /**
   * Format bytes to human readable format
   */
  static formatBytes(bytes: number): string {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  }
}