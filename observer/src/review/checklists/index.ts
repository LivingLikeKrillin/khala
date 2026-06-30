/**
 * 체크리스트 레지스트리
 *
 * PR 타입별 체크리스트를 하나의 맵으로 export한다.
 */

import type { PrType } from '../types.js';
import type { ChecklistItem } from '../types.js';
import { domainCrudChecklist } from './domain-crud.js';
import { apiChangeChecklist } from './api-change.js';
import { uiFeatureChecklist } from './ui-feature.js';
import { uiComponentChecklist } from './ui-component.js';
import {
  configChangeChecklist,
  dbMigrationChecklist,
  testOnlyChecklist,
  docsOnlyChecklist,
  designSystemChecklist,
  generalChecklist,
} from './others.js';

/** PR 타입별 체크리스트 맵 */
export const CHECKLISTS: Record<PrType, ChecklistItem[]> = {
  'domain-crud': domainCrudChecklist,
  'api-change': apiChangeChecklist,
  'config-change': configChangeChecklist,
  'db-migration': dbMigrationChecklist,
  'ui-feature': uiFeatureChecklist,
  'ui-component': uiComponentChecklist,
  'design-system': designSystemChecklist,
  'test-only': testOnlyChecklist,
  'docs-only': docsOnlyChecklist,
  'general': generalChecklist,
};
