import { StationInfo } from '@/types';

// UI-only labels keyed by the station IDs used by the API. Keeping the IDs as
// option values means requests and persisted task data remain unchanged.
const STATION_NAMES_ZH_TW: Readonly<Record<number, string>> = {
  1: '南港',
  2: '台北',
  3: '板橋',
  4: '桃園',
  5: '新竹',
  6: '苗栗',
  7: '台中',
  8: '彰化',
  9: '雲林',
  10: '嘉義',
  11: '台南',
  12: '左營',
};

export const getStationDisplayName = (station: StationInfo): string => {
  return STATION_NAMES_ZH_TW[station.id] || station.name;
};

// Utility function to get the localized station name by ID
export const getStationName = (stationId: number, stations: StationInfo[] = []): string => {
  const station = stations.find(s => s.id === stationId);
  return STATION_NAMES_ZH_TW[stationId] || station?.name || `站點 ${stationId}`;
};

// Utility function to format station route
export const formatStationRoute = (fromStation: number, toStation: number, stations: StationInfo[] = []): string => {
  const fromName = getStationName(fromStation, stations);
  const toName = getStationName(toStation, stations);
  return `${fromName} → ${toName}`;
};
