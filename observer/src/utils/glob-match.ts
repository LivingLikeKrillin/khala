/**
 * 간단한 glob 패턴 매칭 유틸
 *
 * 외부 의존성 없이 파일 경로를 glob 패턴과 매칭한다.
 * 지원 패턴: *, **, ?
 */

/**
 * glob 패턴을 정규식으로 변환한다.
 */
function globToRegex(pattern: string): RegExp {
  // 경로 구분자를 정규화
  const normalized = pattern.replace(/\\/g, '/');

  let regex = '';
  let i = 0;

  while (i < normalized.length) {
    const char = normalized[i]!;

    if (char === '*') {
      if (normalized[i + 1] === '*') {
        // ** — 디렉토리 깊이 무제한 매칭
        if (normalized[i + 2] === '/') {
          regex += '(?:.+/)?';
          i += 3;
        } else {
          regex += '.*';
          i += 2;
        }
      } else {
        // * — 단일 세그먼트 내 매칭 (슬래시 제외)
        regex += '[^/]*';
        i += 1;
      }
    } else if (char === '?') {
      regex += '[^/]';
      i += 1;
    } else if (char === '.') {
      regex += '\\.';
      i += 1;
    } else {
      regex += char;
      i += 1;
    }
  }

  return new RegExp(`^${regex}$`);
}

/**
 * 파일 경로가 glob 패턴과 매칭되는지 확인한다.
 *
 * @param filePath 검사할 파일 경로
 * @param pattern glob 패턴
 */
export function globMatch(filePath: string, pattern: string): boolean {
  const normalizedPath = filePath.replace(/\\/g, '/');
  const regex = globToRegex(pattern);
  return regex.test(normalizedPath);
}
