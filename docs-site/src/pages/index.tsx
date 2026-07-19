import React from 'react';
import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';

// NOTE: Plan 20 T7 rewrites this into a full editorial homepage
// (hero + Two Faces ARX section + red-lines callout + getting-started cards).
// This stub gives the site a valid `/` route for the T2-T4 slice.

export default function Home(): ReactNode {
  return (
    <Layout
      title="custos — the non-custodial execution runner"
      description="Local daemon that holds your keys, runs your strategies, and reports signed execution facts. Apache-2.0.">
      <main
        style={{
          maxWidth: 860,
          margin: '96px auto 120px',
          padding: '0 32px',
        }}>
        <div
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--ifm-color-content-secondary)',
            marginBottom: 32,
          }}>
          Part of The Alephain Guild ecosystem
        </div>

        <h1
          style={{
            fontFamily: 'Newsreader, serif',
            fontWeight: 300,
            fontSize: 'clamp(36px, 5vw, 64px)',
            letterSpacing: '-0.01em',
            lineHeight: 1.1,
            margin: 0,
          }}>
          custos <em style={{color: 'var(--ifm-color-primary)', fontStyle: 'italic'}}>—</em>{' '}
          the non-custodial execution runner
        </h1>

        <p
          style={{
            fontSize: 18,
            lineHeight: 1.65,
            marginTop: 28,
            color: 'var(--ifm-color-content-secondary)',
          }}>
          Local daemon that holds your keys, runs your strategies, and reports
          signed execution facts. Runs on your machine; never hosted by the
          Guild.
        </p>

        <div
          style={{
            marginTop: 40,
            display: 'flex',
            gap: 16,
            flexWrap: 'wrap',
          }}>
          <Link
            className="button button--primary button--lg"
            to="/02-getting-started/installation">
            Get started →
          </Link>
          <Link
            className="button button--outline button--lg"
            to="/05-trust-model/red-lines">
            Read the trust model
          </Link>
          <a
            className="button button--outline button--lg"
            href="https://github.com/alchymia-labs/custos">
            GitHub ↗
          </a>
        </div>

        <hr style={{margin: '72px 0'}} />

        <div
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--ifm-color-content-secondary)',
            marginBottom: 12,
          }}>
          Notice
        </div>
        <h2 style={{marginTop: 0}}>Site under construction</h2>
        <p style={{color: 'var(--ifm-color-content-secondary)'}}>
          The full documentation site is being scaffolded per{' '}
          <a href="https://github.com/alchymia-labs/custos/blob/main/.forge/plans/2026-07/20-custos-docs-site-scaffold.md">
            Plan 20
          </a>
          . Session 1 (T2–T4) lands this skeleton; content migration (T5) and
          the full homepage (T7) follow in subsequent sessions. See the{' '}
          <Link to="/01-introduction/what-is-custos">Introduction</Link> for the
          current shape of each chapter.
        </p>
      </main>
    </Layout>
  );
}
