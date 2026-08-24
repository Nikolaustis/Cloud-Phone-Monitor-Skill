// Source-only fallback placeholders.
// Real dashboard data is generated at runtime into dashboard_data/ and is not
// committed to the source repository.

export const latestRun = {
  outputDir: "",
  generatedAt: "",
  status: "not_loaded",
  currencies: [],
  recordsByPlatform: {},
  aggregatedRowsByPlatform: {},
  baselineRowsByPlatform: {},
  platformSessionStatus: {},
  internalPages: {},
  baselineMonitor: {},
  qualityPriceMonitor: {},
  outputFiles: [],
};

export const platformCards = [];
export const pairingSuggestions = [];
export const qualityRows = [];
export const relativeIndexData = [];
export const rationalityRows = [];
export const dailyTables = [];
