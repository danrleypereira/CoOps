import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchData, filterMetadata, getDataBasePath } from './dataSource';

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

  describe('fetchData', () => {
    beforeEach(() => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
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

    test('inclui o status HTTP na mensagem quando statusText está vazio', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: '' }));

      await expect(fetchData('silver/missing.json')).rejects.toThrow(
        /Failed to fetch .*silver\/missing\.json \(status: 404\)$/
      );
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
