/**
 * The basemap picker sets "genomeOS" in its catalog labels in the wordmark type, like every other
 * visible project name (site.spec.ts, "visible project names use the wordmark typography"). The
 * closed trigger shows the selected basemap, "genomeOS Dark" by default, on /app/ at load.
 */
import { createElement, Fragment } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import {
  BASEMAP_OPTIONS,
  TERRAIN_OPTIONS,
  type BasemapId,
  type TerrainId,
} from '../src/atlas/earth-style-catalog';
import {
  EarthStylePicker,
  withWordmark,
} from '../src/components/atlas/EarthStylePicker';
import { EscapeStackProvider } from '../src/components/atlas/useEscapeStack';

const markup = (text: string) =>
  renderToStaticMarkup(createElement(Fragment, null, withWordmark(text)));

describe('withWordmark', () => {
  it('wraps each genomeOS in the wordmark and keeps the rest of the label', () => {
    expect(markup('genomeOS Dark')).toBe(
      '<span class="brand-name">genomeOS</span> Dark',
    );
    expect(markup('genomeOS')).toBe('<span class="brand-name">genomeOS</span>');
    expect(markup('a genomeOS b genomeOS')).toBe(
      'a <span class="brand-name">genomeOS</span> b <span class="brand-name">genomeOS</span>',
    );
  });

  it('returns labels without the name unchanged', () => {
    expect(withWordmark('Bing Maps Aerial')).toBe('Bing Maps Aerial');
  });
});

describe('the closed basemap trigger', () => {
  it('shows the default genomeOS Dark basemap with the wordmark', () => {
    const all = <T extends string>(ids: readonly { id: T }[]) =>
      Object.fromEntries(ids.map(({ id }) => [id, true])) as Record<T, boolean>;
    const html = renderToStaticMarkup(
      createElement(
        EscapeStackProvider,
        null,
        createElement(EarthStylePicker, {
          basemap: 'dark-streets' as BasemapId,
          terrain: 'smooth-globe' as TerrainId,
          capabilities: {
            basemaps: all(BASEMAP_OPTIONS),
            terrains: all(TERRAIN_OPTIONS),
          },
          disabled: false,
          onBasemap: () => {},
          onTerrain: () => {},
        }),
      ),
    );
    expect(html).toContain(
      '<strong><span class="brand-name">genomeOS</span> Dark</strong>',
    );
    expect(html).not.toMatch(/<strong>genomeOS/);
  });
});
