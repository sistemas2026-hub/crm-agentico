import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { stopTimer, getTimesheet } = await import('$lib/server/v2/timesheet.js');
// Cast rather than shaping a full Cookies mock, matching leads.test.js and
// tags.test.js: stopTimer only ever calls `cookies.get`, and `apiRequest`
// itself is mocked above, so nothing here touches
// `getAll`/`set`/`delete`/`serialize`. Without the cast svelte-check flags
// this object against SvelteKit's full `Cookies` type on every call site
// below, which is noise for a shape the test deliberately keeps minimal.
const event = /** @type {any} */ ({ cookies: { get: () => 'token' } });

describe('stopTimer', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('POSTs to the stop endpoint for the given entry', async () => {
    apiRequest.mockResolvedValue({ id: 'e1', ended_at: '2026-08-04T10:00:00Z' });
    const result = await stopTimer(event, 'e1');

    const [endpoint, options] = apiRequest.mock.calls[0];
    expect(endpoint).toBe('/time-entries/e1/stop/');
    expect(options.method).toBe('POST');
    expect(result.ended_at).toBeTruthy();
  });

  it('refuses a missing entry id rather than posting to a malformed path', async () => {
    await expect(stopTimer(event, '')).rejects.toThrow(/registro/i);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

/**
 * The default week is the COMPANY's (27/10/2026). The server runs in UTC: on
 * Sunday from 19:00 in Bogotá `new Date()` is already Monday, and the page
 * opened on next week. Asserted on the range that reaches the API.
 */
describe('getTimesheet default week', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});
  });

  const range = () => {
    const qs = new URLSearchParams(String(apiRequest.mock.calls[0][0]).split('?')[1]);
    return { start: qs.get('start'), end: qs.get('end') };
  };

  it("a company Sunday ends ITS week, it does not start the next one", async () => {
    // Sunday 2026-11-01, 19:30 in Bogotá: already Monday in the server's UTC.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-02T00:30:00Z'));
    try {
      await getTimesheet(event, { hoy: '2026-11-01' });
    } finally {
      vi.useRealTimers();
    }
    expect(range()).toEqual({ start: '2026-10-26', end: '2026-11-01' });
  });

  it('an explicit week is left alone', async () => {
    await getTimesheet(event, { start: '2026-01-05', end: '2026-01-11', hoy: '2026-11-01' });
    expect(range()).toEqual({ start: '2026-01-05', end: '2026-01-11' });
  });
});
