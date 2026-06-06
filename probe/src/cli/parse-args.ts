/**
 * CLI 인자 파서
 */

export type OutputFormat = 'markdown' | 'json' | 'brief';

export interface TroubleshootCliOptions {
  signal: string;
  kind?: 'stacktrace' | 'error' | 'test-failure' | 'incident';
  diffBase?: string;
  suspectServices: string[];
  format: OutputFormat;
}

/**
 * troubleshoot 커맨드 인자를 파싱한다.
 * 비-플래그 토큰은 신호로 합친다 (인자 우선; stdin은 호출부에서 fallback).
 */
export function parseTroubleshootArgs(args: string[]): TroubleshootCliOptions {
  const o: TroubleshootCliOptions = { signal: '', kind: undefined, suspectServices: [], format: 'markdown' };
  const signalParts: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--kind' && i + 1 < args.length) {
      const k = args[++i]!;
      if (k === 'stacktrace' || k === 'error' || k === 'test-failure' || k === 'incident') o.kind = k;
    } else if (arg === '--diff-base' && i + 1 < args.length) {
      o.diffBase = args[++i]!;
    } else if (arg === '--suspect' && i + 1 < args.length) {
      o.suspectServices.push(args[++i]!);
    } else if (arg === '--format' && i + 1 < args.length) {
      const f = args[++i]!;
      if (f === 'markdown' || f === 'json' || f === 'brief') o.format = f;
    } else if (!arg.startsWith('--')) {
      signalParts.push(arg);
    }
  }
  o.signal = signalParts.join(' ');
  return o;
}

export interface CliOptions {
  base: string;
  format: OutputFormat;
  silent: boolean;
  spec: string;
}

/**
 * CLI 인자를 파싱한다.
 */
export function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {
    base: 'origin/main',
    format: 'markdown',
    silent: false,
    spec: '',
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--base' && i + 1 < args.length) {
      options.base = args[i + 1]!;
      i++;
    } else if (arg === '--format' && i + 1 < args.length) {
      const fmt = args[i + 1]!;
      if (fmt === 'markdown' || fmt === 'json' || fmt === 'brief') {
        options.format = fmt;
      }
      i++;
    } else if (arg === '--spec' && i + 1 < args.length) {
      options.spec = args[i + 1]!;
      i++;
    } else if (arg === '--silent') {
      options.silent = true;
    } else if (!arg.startsWith('--') && !options.spec) {
      options.spec = arg;
    }
  }

  return options;
}
