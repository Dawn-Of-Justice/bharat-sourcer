import type { BuildGuide } from './api'

// Sample build guide for ?preview=1 (docs/contracts/build-guide.md). Dummy steps for the UI preview only: not written
// from a real video or checked against any build. Every title ends in "(demo)", as the backend's demo guide does.
export function sampleBuildGuide(): BuildGuide {
  return {
    status: 'ready',
    message: 'Dummy sample steps for the local preview; not written from a real video and not verified.',
    generated_at: new Date().toISOString(),
    items_hash: 'dummy',
    demo: true,
    steps: [
      {
        title: 'Lay out and check the parts (demo)',
        detail:
          'Dummy step: put every part on the bench and compare it with the checklist above. Check the sample sensor module’s pins before soldering anything.',
        line_ids: ['L01', 'L02'],
        timestamp: '00:42',
        caution: null,
        origin: 'ai_inferred',
      },
      {
        title: 'Solder the headers (demo)',
        detail:
          'Dummy step: solder the pin headers to the sample controller board and the sensor module, one pin first, then the rest.',
        line_ids: ['L01', 'L02'],
        timestamp: '01:12',
        caution: 'Dummy caution: a hot iron burns; let joints cool before handling the board.',
        origin: 'ai_inferred',
      },
      {
        title: 'Wire the sensor to the controller (demo)',
        detail:
          'Dummy step: connect power, ground and the two I2C lines with jumper wires, following the wiring drawing below.',
        line_ids: ['L02', 'L03'],
        timestamp: '1:03:05',
        caution: null,
        origin: 'ai_inferred',
      },
      {
        title: 'Flash the sample code and test (demo)',
        detail:
          'Dummy step: upload the project’s code over USB, open the serial monitor and check that sensor readings appear.',
        line_ids: ['L01'],
        timestamp: null,
        caution: 'Dummy caution: unplug the battery while the board is on USB.',
        origin: 'ai_inferred',
      },
    ],
  }
}
