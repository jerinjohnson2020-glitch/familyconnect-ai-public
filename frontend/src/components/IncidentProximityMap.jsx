import React, { useState } from 'react';
import { MapPin, Navigation, RefreshCw, AlertTriangle, CheckCircle2, ExternalLink, Clock } from 'lucide-react';
import { updateIncidentLocation } from '../services/api';

export default function IncidentProximityMap({
  incident,
  allResponders = [],
  canRefreshLocation = false,
  onLocationUpdated = null
}) {
  const [hoveredUnit, setHoveredUnit] = useState(null);
  const [mapMode, setMapMode] = useState('osm'); // 'osm' (Real OpenStreetMap) | 'radar' (Tactical Haversine Vector)
  const [gpsRefreshState, setGpsRefreshState] = useState('idle'); // 'idle' | 'requesting' | 'updated' | 'denied' | 'unavailable' | 'timeout'
  const [gpsStatusMsg, setGpsStatusMsg] = useState('');

  if (!incident) return null;

  const hasValidCoordinates =
    typeof incident.latitude === 'number' &&
    typeof incident.longitude === 'number' &&
    !Number.isNaN(incident.latitude) &&
    !Number.isNaN(incident.longitude);

  const centerLat = hasValidCoordinates ? incident.latitude : 0;
  const centerLon = hasValidCoordinates ? incident.longitude : 0;

  // Check if location timestamp is stale (> 5 minutes old during an active incident)
  const locTimestamp = incident.location_updated_at || incident.created_at;
  const locAgeMinutes = locTimestamp
    ? Math.max(0, Math.round((Date.now() - new Date(locTimestamp).getTime()) / 60000))
    : null;
  const isLocationStale = incident.status !== 'RESOLVED' && locAgeMinutes !== null && locAgeMinutes >= 5;

  // OpenStreetMap bounding box (~0.015 deg around incident coordinates)
  const delta = 0.015;
  const bbox = `${(centerLon - delta).toFixed(6)}%2C${(centerLat - delta).toFixed(6)}%2C${(centerLon + delta).toFixed(6)}%2C${(centerLat + delta).toFixed(6)}`;
  const osmEmbedUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${centerLat.toFixed(6)}%2C${centerLon.toFixed(6)}`;
  const osmFullUrl = `https://www.openstreetmap.org/?mlat=${centerLat.toFixed(6)}&mlon=${centerLon.toFixed(6)}#map=15/${centerLat.toFixed(6)}/${centerLon.toFixed(6)}`;

  // Phase 5A: Refresh live device coordinates via Browser Geolocation API (no silent fallback)
  const handleRefreshLiveGps = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGpsRefreshState('unavailable');
      setGpsStatusMsg('Browser Geolocation API is unavailable in this environment. Existing coordinates retained.');
      return;
    }

    setGpsRefreshState('requesting');
    setGpsStatusMsg('Requesting live Browser GPS fix...');

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = parseFloat(pos.coords.latitude.toFixed(6));
        const lon = parseFloat(pos.coords.longitude.toFixed(6));
        const accuracy = pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null;
        try {
          const updated = await updateIncidentLocation(incident.id, {
            latitude: lat,
            longitude: lon,
            location_accuracy_m: accuracy,
            location_source: 'browser_gps',
            location_label: `Live GPS Refresh (${lat.toFixed(4)}, ${lon.toFixed(4)})`
          });
          setGpsRefreshState('updated');
          setGpsStatusMsg(`Live GPS updated: (${lat}, ${lon})${accuracy ? ` ±${accuracy}m` : ''}`);
          if (onLocationUpdated) onLocationUpdated(updated);
        } catch (err) {
          setGpsRefreshState('unavailable');
          setGpsStatusMsg(`Failed to persist GPS update: ${err.message}`);
        }
      },
      (err) => {
        if (err.code === 1) {
          setGpsRefreshState('denied');
          setGpsStatusMsg('Location permission denied. No fake coordinates substituted.');
        } else if (err.code === 3) {
          setGpsRefreshState('timeout');
          setGpsStatusMsg('GPS fix timed out. Retry in an area with clear sky view.');
        } else {
          setGpsRefreshState('unavailable');
          setGpsStatusMsg(`GPS position unavailable (${err.message || 'sensor error'}).`);
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  // 1 degree latitude ~ 111 km.
  const mapWidth = 440;
  const mapHeight = 240;
  const cx = mapWidth / 2;
  const cy = mapHeight / 2;
  const scale = 50;

  const getCoordinates = (lat, lon) => {
    const dLatKm = (lat - centerLat) * 111.0;
    const dLonKm = (lon - centerLon) * (111.0 * Math.cos((centerLat * Math.PI) / 180.0));
    const x = cx + dLonKm * scale;
    const y = cy - dLatKm * scale;
    return {
      x: Math.max(25, Math.min(mapWidth - 25, x)),
      y: Math.max(25, Math.min(mapHeight - 25, y))
    };
  };

  // Phase 5A: Only plot responders that have genuine stored coordinates (NEVER invent coordinates with Math.random)
  const displayUnits = (incident.matched_responders || [])
    .map(mr => {
      const full = allResponders.find(r => r.id === mr.responder_id) || {};
      const hasRealCoords = typeof full.latitude === 'number' && typeof full.longitude === 'number';
      return {
        id: mr.responder_id,
        name: mr.name,
        role: mr.role,
        phone: mr.phone,
        skills: mr.skills,
        distance_km: mr.distance_km,
        status: mr.status,
        latitude: hasRealCoords ? full.latitude : null,
        longitude: hasRealCoords ? full.longitude : null
      };
    })
    .filter(u => u.latitude !== null && u.longitude !== null);

  return (
    <div style={{
      background: 'var(--bg-primary)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '0.85rem',
      marginTop: '0.65rem',
      position: 'relative'
    }}>
      {/* Header bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '0.5rem',
        marginBottom: '0.55rem',
        fontSize: '0.75rem',
        color: 'var(--text-secondary)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
          <Navigation size={13} color="var(--color-primary)" />
          <strong style={{ color: 'var(--color-text)' }}>Live Incident Geolocation & Map</strong>
          <span style={{
            fontSize: '0.66rem',
            padding: '0.1rem 0.45rem',
            borderRadius: '4px',
            background: incident.location_source === 'browser_gps' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(56, 189, 248, 0.12)',
            color: incident.location_source === 'browser_gps' ? '#34d399' : '#38bdf8',
            border: '1px solid rgba(56, 189, 248, 0.25)'
          }}>
            Source: {incident.location_source || 'manual'}
            {incident.location_accuracy_m != null ? ` (±${Math.round(incident.location_accuracy_m)}m)` : ''}
          </span>
          {isLocationStale && (
            <span style={{
              fontSize: '0.66rem',
              padding: '0.1rem 0.45rem',
              borderRadius: '4px',
              background: 'rgba(245, 158, 11, 0.15)',
              color: '#fbbf24',
              border: '1px solid rgba(245, 158, 11, 0.35)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem'
            }}>
              <Clock size={10} /> Stale fix ({locAgeMinutes}m old)
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={mapMode === 'osm' ? 'btn-primary' : 'btn-secondary'}
            style={{ fontSize: '0.68rem', padding: '0.15rem 0.5rem' }}
            onClick={() => setMapMode('osm')}
          >
            OpenStreetMap
          </button>
          <button
            type="button"
            className={mapMode === 'radar' ? 'btn-primary' : 'btn-secondary'}
            style={{ fontSize: '0.68rem', padding: '0.15rem 0.5rem' }}
            onClick={() => setMapMode('radar')}
          >
            Responder Vector Plot ({displayUnits.length})
          </button>
          {canRefreshLocation && incident.status !== 'RESOLVED' && (
            <button
              type="button"
              className="btn-secondary"
              style={{ fontSize: '0.68rem', padding: '0.15rem 0.55rem', borderColor: 'var(--color-primary)', color: 'var(--color-primary)' }}
              onClick={handleRefreshLiveGps}
              disabled={gpsRefreshState === 'requesting'}
            >
              <RefreshCw size={10} /> {gpsRefreshState === 'requesting' ? 'Updating GPS...' : 'Refresh Live GPS'}
            </button>
          )}
        </div>
      </div>

      {/* GPS Refresh Feedback Banner */}
      {gpsStatusMsg && (
        <div style={{
          fontSize: '0.72rem',
          padding: '0.35rem 0.6rem',
          borderRadius: '5px',
          marginBottom: '0.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.35rem',
          background: gpsRefreshState === 'updated' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
          color: gpsRefreshState === 'updated' ? '#34d399' : '#fca5a5',
          border: gpsRefreshState === 'updated' ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(239, 68, 68, 0.3)'
        }}>
          {gpsRefreshState === 'updated' ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
          <span>{gpsStatusMsg}</span>
        </div>
      )}

      {!hasValidCoordinates ? (
        <div style={{
          padding: '1.5rem',
          textAlign: 'center',
          color: '#fca5a5',
          background: 'rgba(239, 68, 68, 0.08)',
          borderRadius: '6px',
          fontSize: '0.8rem'
        }}>
          No valid coordinates recorded for this incident. Click &ldquo;Refresh Live GPS&rdquo; to acquire real device coordinates.
        </div>
      ) : mapMode === 'osm' ? (
        <div style={{ position: 'relative', width: '100%', borderRadius: '6px', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
          <iframe
            title={`OpenStreetMap for Incident #${incident.id}`}
            src={osmEmbedUrl}
            style={{ width: '100%', height: '230px', border: 0, display: 'block', background: '#0f172a' }}
            loading="lazy"
          />
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.35rem 0.6rem',
            background: 'rgba(15, 23, 42, 0.92)',
            fontSize: '0.7rem',
            color: '#cbd5e1',
            flexWrap: 'wrap',
            gap: '0.4rem'
          }}>
            <span>
              <MapPin size={11} color="#ef4444" style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
              <strong>{incident.location_label}</strong> ({centerLat.toFixed(5)}, {centerLon.toFixed(5)})
            </span>
            <a
              href={osmFullUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#38bdf8', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontWeight: 600 }}
            >
              Open Full Map <ExternalLink size={11} />
            </a>
          </div>
        </div>
      ) : (
        <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: '6px' }}>
          <svg
            viewBox={`0 0 ${mapWidth} ${mapHeight}`}
            style={{
              width: '100%',
              height: 'auto',
              maxHeight: '230px',
              background: 'radial-gradient(circle at center, #0e182e 0%, #080d19 100%)',
              display: 'block'
            }}
            aria-label="Proximity vector plot showing verified incident and responder coordinates"
          >
            {/* Concentric Haversine Distance Rings */}
            <circle cx={cx} cy={cy} r={scale * 0.5} fill="none" stroke="#1e2c47" strokeWidth="1" strokeDasharray="3,3" />
            <circle cx={cx} cy={cy} r={scale * 1.0} fill="none" stroke="#1e2c47" strokeWidth="1" strokeDasharray="4,4" />
            <circle cx={cx} cy={cy} r={scale * 1.8} fill="none" stroke="#1e2c47" strokeWidth="1" strokeDasharray="4,4" />

            <text x={cx + scale * 0.5 + 4} y={cy - 4} fill="#475569" fontSize="8" fontWeight="600">0.5 km</text>
            <text x={cx + scale * 1.0 + 4} y={cy - 4} fill="#475569" fontSize="8" fontWeight="600">1.0 km</text>
            <text x={cx + scale * 1.8 + 4} y={cy - 4} fill="#475569" fontSize="8" fontWeight="600">1.8 km</text>

            <line x1={cx} y1={10} x2={cx} y2={mapHeight - 10} stroke="#162238" strokeWidth="1" />
            <line x1={10} y1={cy} x2={mapWidth - 10} y2={cy} stroke="#162238" strokeWidth="1" />

            {/* Incident Pin (Center) */}
            <g>
              <circle cx={cx} cy={cy} r="14" fill="rgba(239, 68, 68, 0.2)">
                <animate attributeName="r" values="8;18;8" dur="2.4s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.8;0.1;0.8" dur="2.4s" repeatCount="indefinite" />
              </circle>
              <circle cx={cx} cy={cy} r="6" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
              <text x={cx} y={cy + 18} fill="#fca5a5" fontSize="9" fontWeight="700" textAnchor="middle">
                Incident ({incident.reporter_name.split(' ')[0]})
              </text>
            </g>

            {/* Verified Responder Units */}
            {displayUnits.map((unit, idx) => {
              const pos = getCoordinates(unit.latitude, unit.longitude);
              const isHovered = hoveredUnit?.id === unit.id;
              const isActiveUnit = ['ASSIGNED', 'ACCEPTED', 'EN_ROUTE', 'ARRIVED', 'RECOMMENDED'].includes(unit.status);

              return (
                <g
                  key={idx}
                  onMouseEnter={() => setHoveredUnit(unit)}
                  onMouseLeave={() => setHoveredUnit(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <line
                    x1={cx}
                    y1={cy}
                    x2={pos.x}
                    y2={pos.y}
                    stroke={isActiveUnit ? 'rgba(56, 189, 248, 0.35)' : 'rgba(100, 116, 139, 0.25)'}
                    strokeWidth="1"
                    strokeDasharray="2,2"
                  />
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={isHovered ? 8 : 6}
                    fill={isActiveUnit ? '#0284c7' : '#475569'}
                    stroke={isHovered ? '#38bdf8' : '#ffffff'}
                    strokeWidth="1.5"
                  />
                  <text
                    x={pos.x}
                    y={pos.y - 10}
                    fill={isHovered ? '#38bdf8' : '#e2e8f0'}
                    fontSize="8.5"
                    fontWeight="600"
                    textAnchor="middle"
                  >
                    {unit.name.split(' ')[0]} ({unit.distance_km}km)
                  </text>
                </g>
              );
            })}
          </svg>

          {hoveredUnit && (
            <div style={{
              position: 'absolute',
              bottom: '8px',
              left: '8px',
              right: '8px',
              background: 'rgba(15, 23, 42, 0.95)',
              border: '1px solid #38bdf8',
              borderRadius: '6px',
              padding: '0.45rem 0.65rem',
              fontSize: '0.75rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div>
                <strong style={{ color: '#ffffff' }}>{hoveredUnit.name}</strong>{' '}
                <span style={{ color: '#94a3b8' }}>({hoveredUnit.role})</span>
                <div style={{ color: '#cbd5e1', fontSize: '0.7rem' }}>
                  Coords: ({hoveredUnit.latitude.toFixed(4)}, {hoveredUnit.longitude.toFixed(4)}) • Skills: {hoveredUnit.skills}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ color: '#38bdf8', fontWeight: 800 }}>{hoveredUnit.distance_km} km</span>
                <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>
                  ● {hoveredUnit.status}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Telemetry Footer */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '0.4rem',
        marginTop: '0.45rem',
        fontSize: '0.68rem',
        color: 'var(--text-muted)'
      }}>
        <span>
          Coordinates: {centerLat.toFixed(5)}, {centerLon.toFixed(5)}
          {locTimestamp ? ` • Updated: ${new Date(locTimestamp).toLocaleTimeString()}` : ''}
        </span>
        <span>Zero synthetic coordinates • Verified DB records only</span>
      </div>
    </div>
  );
}

