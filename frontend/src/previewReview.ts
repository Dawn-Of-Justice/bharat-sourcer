import type { BomItem, Job } from './api'

// Dummy review-stage fixtures for ?preview=1 (v0.20/v0.21 review fields). Every value is sample data, not a real check.
export function reviewItems(items: BomItem[]): BomItem[] {
  const [board, sensor, wires] = items
  return [
    {
      ...board,
      confidence: 'verified',
      confidence_reason: 'Dummy reason: code evidence and the video agree.',
      evidence: [
        { source: 'video', timestamp: '01:12', observation: 'Dummy: the sample board is shown on the bench.' },
        {
          source: 'code',
          file: 'src/main.cpp',
          line: 3,
          quote: '#include <SampleBoard.h>',
          url: 'https://example.com/dummy/src/main.cpp#L3',
          observation: 'Dummy: the sample code includes the board library.',
          timestamp: null,
        },
      ],
      buyable_spec: {
        origin: 'ai_inferred',
        category: 'board',
        mount: 'any',
        mount_origin: 'default',
        params: [
          {
            name: 'logic voltage',
            value: '3.3V',
            operator: 'equals',
            unit: 'V',
            si_value: 3.3,
            required: true,
            origin: 'inferred',
            reason: 'Dummy reason: the sample project runs at 3.3 V.',
          },
        ],
        needs_value: false,
      },
    },
    {
      ...sensor,
      confidence: 'likely',
      confidence_reason:
        'Dummy reason: the video description names the sensor, but its exact variant still needs checking.',
      evidence: [
        {
          source: 'youtube_description',
          quote: 'Sample sensor module (dummy listing)',
          url: 'https://example.com/dummy-video',
          observation: 'Dummy: listed in the sample video description.',
          timestamp: null,
        },
      ],
      lookalikes: [
        { name: 'Sample sensor B', note: 'Dummy note: same footprint, different chip.', origin: 'table' },
        { name: 'Sample sensor C', note: null, origin: 'ai' },
      ],
    },
    {
      ...wires,
      buyable_spec: {
        origin: 'ai_inferred',
        category: 'wire',
        mount: 'any',
        mount_origin: 'default',
        params: [],
        needs_value: true,
        needs_value_reason: 'Dummy reason: the sample source does not state the jumper-wire length.',
      },
    },
  ]
}

export const reviewJobFields: Pick<Job, 'safety_flags' | 'source_reports' | 'video_meta'> = {
  safety_flags: [
    {
      code: 'LEVEL_SHIFT',
      severity: 'caution',
      title: 'Dummy: 3.3 V and 5 V parts are mixed',
      message: 'Dummy preview flag: the sample board runs at 3.3 V logic and the sample sensor expects 5 V.',
      guidance: ['Dummy: route every mixed signal through a level shifter.'],
      line_ids: ['L01', 'L02'],
      triggers: [{ line_id: 'L01', field: 'requirements[0]', matched: '3.3 V' }],
      method: 'deterministic_rules',
      rule_version: 'dummy',
    },
    {
      code: 'LIPO',
      severity: 'warning',
      title: 'Dummy: lithium cell without a listed charger',
      message:
        'Dummy preview flag: the sample project mentions a 3.7 V Li-ion cell but no charger or protection board.',
      guidance: ['Dummy: use a protected cell.', 'Dummy: add a charger module with protection.'],
      line_ids: [],
      triggers: [{ line_id: null, field: 'project.power', matched: '3.7 V Li-ion' }],
      method: 'deterministic_rules',
      rule_version: 'dummy',
    },
  ],
  source_reports: [
    {
      url: 'https://example.com/dummy-video',
      kind: 'video',
      role: 'primary',
      status: 'read',
      item_count: 3,
      code_item_count: 0,
      error: null,
      found_in: null,
    },
    {
      url: 'https://example.com/dummy-video',
      kind: 'youtube_description',
      role: 'additional',
      status: 'read',
      item_count: 1,
      code_item_count: 0,
      error: null,
      found_in: null,
    },
    {
      url: 'https://github.com/example/dummy-repo',
      kind: 'github',
      role: 'additional',
      status: 'read',
      item_count: 1,
      code_item_count: 1,
      error: null,
      found_in: 'youtube_description',
    },
    {
      url: 'https://example.com/dummy-blog-post',
      kind: 'blog',
      role: 'additional',
      status: 'failed',
      item_count: 0,
      error: { code: 'SOURCE_UNAVAILABLE', message: 'Dummy: the sample blog could not be read.' },
      found_in: null,
    },
  ],
  video_meta: {
    video_id: 'dummyvideo1',
    title: 'Dummy video',
    channel: 'Dummy channel',
    fetched_at: new Date().toISOString(),
    expired: false,
    links: [
      { url: 'https://github.com/example/dummy-repo', kind: 'project_source', followed: true },
      { url: 'https://example.com/dummy-shop-link', kind: 'store', followed: false },
    ],
  },
}
