/**
 * Karax 로거 유틸
 *
 * console.log 직접 사용 금지 규칙에 따른 래퍼.
 */

/** 로그 레벨 */
type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

let currentLevel: LogLevel = 'info';
let silent = false;

/**
 * 로그 레벨을 설정한다.
 */
export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
}

/**
 * 로그 출력을 완전히 억제한다.
 */
export function setSilent(value: boolean): void {
  silent = value;
}

function shouldLog(level: LogLevel): boolean {
  if (silent) return false;
  return LOG_LEVEL_PRIORITY[level] >= LOG_LEVEL_PRIORITY[currentLevel];
}

/** 디버그 로그 */
export function debug(message: string, ...args: unknown[]): void {
  if (shouldLog('debug')) {
    process.stderr.write(`[karax:debug] ${message} ${args.map(String).join(' ')}\n`);
  }
}

/** 정보 로그 */
export function info(message: string): void {
  if (shouldLog('info')) {
    process.stdout.write(`${message}\n`);
  }
}

/** 경고 로그 */
export function warn(message: string): void {
  if (shouldLog('warn')) {
    process.stderr.write(`⚠️  ${message}\n`);
  }
}

/** 에러 로그 */
export function error(message: string): void {
  if (shouldLog('error')) {
    process.stderr.write(`❌ ${message}\n`);
  }
}

export const logger = { debug, info, warn, error, setLogLevel, setSilent };
