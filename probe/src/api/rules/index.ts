/**
 * 내장 린트 룰 레지스트리
 *
 * 모든 내장 룰을 하나의 배열로 export한다.
 * 규정 문서: docs/karax-v0.2-scope.md § 3.1
 */

import type { LintRule } from '../types.js';
import { fieldTypeRule } from './field-type.js';
import { nullableExplicitRule, noNullableOptionalRule } from './nullable.js';
import { errorResponseSchemaRule } from './error-response.js';
import { paginationRequiredRule } from './pagination.js';
import { pathNamingRule, propertyNamingRule } from './naming.js';
import { enumRequiredRule, exampleRequiredRule } from './enum-example.js';
import { deprecatedLifecycleRule } from './deprecated.js';

/** 모든 내장 린트 룰 */
export const ALL_RULES: LintRule[] = [
  fieldTypeRule,
  nullableExplicitRule,
  noNullableOptionalRule,
  errorResponseSchemaRule,
  paginationRequiredRule,
  pathNamingRule,
  propertyNamingRule,
  enumRequiredRule,
  exampleRequiredRule,
  deprecatedLifecycleRule,
];

export {
  fieldTypeRule,
  nullableExplicitRule,
  noNullableOptionalRule,
  errorResponseSchemaRule,
  paginationRequiredRule,
  pathNamingRule,
  propertyNamingRule,
  enumRequiredRule,
  exampleRequiredRule,
  deprecatedLifecycleRule,
};
