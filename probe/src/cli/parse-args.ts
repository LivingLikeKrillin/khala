/**
 * CLI 인자 파서
 */

export type OutputFormat = 'markdown' | 'json' | 'brief';

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
