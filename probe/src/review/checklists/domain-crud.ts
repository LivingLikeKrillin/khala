/**
 * domain-crud PR 타입 체크리스트
 *
 * 규정 문서: docs/karax-v0.2-scope.md § 3.3
 */

import type { ChecklistItem } from '../types.js';

export const domainCrudChecklist: ChecklistItem[] = [
  // 필수
  {
    id: 'dc-nullable-spec',
    description: '엔티티 필드의 nullable/required가 스펙에 정확히 반영됨 (nullable/required matches spec)',
    automatable: false,
    guidelineRef: '규정 ② § 2.3.1',
    priority: 'required',
  },
  {
    id: 'dc-error-response',
    description: '에러 응답이 ErrorResponse 스키마를 따름 (error responses follow ErrorResponse schema)',
    automatable: false,
    guidelineRef: '규정 ② § 2.3.2',
    priority: 'required',
  },
  {
    id: 'dc-service-test',
    description: '서비스 레이어에 비즈니스 로직 테스트가 있음 (service layer has business logic tests)',
    automatable: true,
    priority: 'required',
  },
  {
    id: 'dc-controller-test',
    description: '컨트롤러에 통합 테스트 또는 API 스펙 테스트가 있음 (controller has integration/API spec tests)',
    automatable: true,
    priority: 'required',
  },
  // 권장
  {
    id: 'dc-dto-validation',
    description: 'DTO에 validation 어노테이션이 있음 (DTOs have validation annotations)',
    automatable: false,
    priority: 'recommended',
  },
  {
    id: 'dc-pagination',
    description: '페이지네이션이 필요한 목록 API에 cursor/offset이 구현됨 (list APIs have pagination)',
    automatable: false,
    guidelineRef: '규정 ② § 2.3.3',
    priority: 'recommended',
  },
];
