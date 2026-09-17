import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  DataNotFoundError,
  fetchAvailableRepoNames,
  fetchData,
  filterMetadata,
  getDataBasePath,
  isDataNotFoundError,
} from './dataSource';

describe('dataSource service', () => {
  describe('filterMetadata', () => {
    test('remove entradas com _metadata', () => {
      const data: Record<string, unknown>[] = [{ id: 1 }, { _metadata: { generated: 'now' } }, { id: 2 }];
      expect(filterMetadata(data)).toEqual([{ id: 1 }, { id: 2 }]);
    });

    test('remove entradas null ou undefined sem lançar erro', () => {
      const data: (Record<string, unknown> | null | undefined)[] = [{ id: 1 }, null, undefined, { id: 2 }];
      expect(filterMetadata(data)).toEqual([{ id: 1 }, { id: 2 }]);
    });
  });

  describe('fetchAvailableRepoNames', () => {
    afterEach(() => {
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    });

    const respond = (body: unknown) =>
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }));

    test('lê silver/available_repos.json pelo dataSource', async () => {
      respond(['repo-a', 'repo-b']);
      await expect(fetchAvailableRepoNames()).resolves.toEqual(['repo-a', 'repo-b']);
      expect(fetch).toHaveBeenCalledWith(`${getDataBasePath()}/silver/available_repos.json`);
    });

    test('tolera uma entrada de _metadata e ignora valores que não são strings', async () => {
      respond([{ _metadata: { extracted_at: 'now' } }, 'repo-a', null, 3, { name: 'x' }, 'repo-b']);
      await expect(fetchAvailableRepoNames()).resolves.toEqual(['repo-a', 'repo-b']);
    });

    test('retorna lista vazia quando o conteúdo não é um array', async () => {
      respond({ repos: ['repo-a'] });
      await expect(fetchAvailableRepoNames()).resolves.toEqual([]);
    });

    test('propaga DataNotFoundError quando o arquivo não existe', async () => {
      vi.spyOn(console, 'warn').mockImplementation(() => {});
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: '' }));
      await expect(fetchAvailableRepoNames()).rejects.toBeInstanceOf(DataNotFoundError);
    });
  });

  describe('fetchData', () => {
    beforeEach(() => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.spyOn(console, 'warn').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    });

    test('busca o caminho relativo à base de dados e retorna o JSON', async () => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [1, 2] });
      vi.stubGlobal('fetch', fetchMock);

      await expect(fetchData('silver/file.json')).resolves.toEqual([1, 2]);
      expect(fetchMock).toHaveBeenCalledWith(`${getDataBasePath()}/silver/file.json`);
    });

    test('lança DataNotFoundError com o caminho e a URL quando o arquivo não existe (404)', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: '' }));

      const error = await fetchData('silver/missing.json').catch((e: unknown) => e);
      expect(error).toBeInstanceOf(DataNotFoundError);
      expect(isDataNotFoundError(error)).toBe(true);
      const notFound = error as DataNotFoundError;
      expect(notFound.name).toBe('DataNotFoundError');
      expect(notFound.path).toBe('silver/missing.json');
      expect(notFound.url).toBe(`${getDataBasePath()}/silver/missing.json`);
      expect(notFound.message).toMatch(/silver\/missing\.json \(status: 404\)$/);
      // um arquivo ainda não gerado não é tratado como erro
      expect(console.error).not.toHaveBeenCalled();
      expect(console.warn).toHaveBeenCalled();
    });

    test('inclui o status HTTP na mensagem quando statusText está vazio', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, statusText: '' }));

      const error = await fetchData('silver/unavailable.json').catch((e: unknown) => e);
      expect(isDataNotFoundError(error)).toBe(false);
      expect((error as Error).message).toMatch(
        /Failed to fetch .*silver\/unavailable\.json \(status: 503\)$/
      );
      expect(console.error).toHaveBeenCalled();
    });

    test('JSON inválido continua sendo um erro comum', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => {
            throw new SyntaxError('Unexpected token < in JSON');
          },
        })
      );

      const error = await fetchData('silver/file.json').catch((e: unknown) => e);
      expect(error).toBeInstanceOf(SyntaxError);
      expect(isDataNotFoundError(error)).toBe(false);
    });

    test('isDataNotFoundError rejeita valores que não são DataNotFoundError', () => {
      expect(isDataNotFoundError(new Error('status: 404'))).toBe(false);
      expect(isDataNotFoundError(null)).toBe(false);
      expect(isDataNotFoundError('silver/x.json')).toBe(false);
    });

    test('inclui status e statusText quando disponível', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Internal Server Error' })
      );

      await expect(fetchData('silver/broken.json')).rejects.toThrow(
        '(status: 500 Internal Server Error)'
      );
    });

    test('propaga erros de rede', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network down')));

      await expect(fetchData('silver/file.json')).rejects.toThrow('Network down');
      expect(console.error).toHaveBeenCalled();
    });
  });
});
