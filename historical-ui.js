(function (root) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const SCHEMA = 'historical-v1';
  const number = value => Number.isFinite(value) ? value : null;
  const unavailable = value => value === null || value === undefined || value === '' ? 'Unavailable' : String(value);
  const escapeCsv = value => {
    const text = value === null || value === undefined ? '' : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };

  function csvForRecords(records, kind) {
    const fields = kind === 'map'
      ? ['record_id', 'event_date', 'date_precision', 'map_inches', 'crest_feet', 'tc_raw', 'tc_units_labeled', 'tc_hours_confirmed', 'periods_rain_raw', 'quality_tier', 'source_workbook', 'source_worksheet', 'source_row', 'source_file_sha256']
      : ['record_id', 'event_date', 'date_precision', 'source_point_id_raw', 'source_point_id_nws', 'source_crest_feet', 'target_point_id_raw', 'target_point_id_nws', 'target_crest_feet', 'lag_raw', 'lag_units_labeled', 'lag_hours_confirmed', 'quality_tier', 'source_workbook', 'source_worksheet', 'source_row', 'source_file_sha256'];
    return [fields.join(','), ...records.map(row => fields.map(field => escapeCsv(row[field])).join(','))].join('\r\n');
  }

  function create(options) {
    const doc = options.document || root.document;
    const fetcher = options.fetch || root.fetch.bind(root);
    const baseUrl = options.baseUrl || 'historical/relationships/v1/';
    const $ = id => doc.getElementById(id);
    const cache = new Map();
    let crosswalkPromise = null;
    let selectionToken = 0;
    let activeGage = '';
    let activeNwsli = '';
    let activePayload = null;
    let activeRelation = null;
    let sortField = 'event_date';
    let sortDirection = 1;
    let selectedRecordId = '';
    let preferredRelationKey = '';

    const status = $('hist-status');
    const title = $('hist-title');
    const meta = $('hist-meta');
    const choices = $('hist-relationships');
    const chart = $('hist-chart');
    const head = $('hist-head');
    const rows = $('hist-rows');
    const exportButton = $('hist-export');
    const retryButton = $('hist-retry');
    retryButton.hidden = true;

    function message(text, state = 'info') {
      status.textContent = text;
      status.className = `historical-status ${state}`;
      retryButton.hidden = state !== 'error';
      choices.replaceChildren();
      chart.replaceChildren();
      head.replaceChildren();
      rows.replaceChildren();
      meta.textContent = '';
      activeRelation = null;
      exportButton.disabled = true;
    }

    async function loadCrosswalk() {
      if (!crosswalkPromise) {
        crosswalkPromise = fetcher(baseUrl + 'crosswalk.json').then(async response => {
          if (!response.ok) throw new Error(`crosswalk HTTP ${response.status}`);
          const value = await response.json();
          if (!Array.isArray(value)) throw new Error('crosswalk is not an array');
          return value;
        }).catch(error => {
          crosswalkPromise = null;
          throw error;
        });
      }
      return crosswalkPromise;
    }

    async function loadPoint(nwsli) {
      if (cache.has(nwsli)) return cache.get(nwsli);
      const response = await fetcher(`${baseUrl}points/${encodeURIComponent(nwsli)}.json`);
      if (!response.ok) throw new Error(`historical data HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload || payload.schema_version !== SCHEMA || payload.nws_point_id !== nwsli || !Array.isArray(payload.map_events) || !Array.isArray(payload.crest_relationships)) {
        throw new Error('historical data schema mismatch');
      }
      cache.set(nwsli, payload);
      return payload;
    }

    function appendText(parent, tag, text, className) {
      const node = doc.createElement(tag);
      node.textContent = text;
      if (className) node.className = className;
      parent.appendChild(node);
      return node;
    }

    function dataRows(relation) {
      return (relation.records || []).filter(row => row.quality_tier === 'B');
    }

    function availableRelations(payload) {
      const relations = [];
      const mapRows = (payload.map_events || []).filter(row => row.quality_tier === 'B');
      if (mapRows.length) relations.push({key: 'map', kind: 'map', label: 'MAP-to-crest', records: mapRows});
      for (const relation of payload.crest_relationships || []) {
        const pairRows = dataRows(relation);
        if (pairRows.length) relations.push({...relation, key: `pair:${relation.relationship_id}`, kind: 'pair', label: `${relation.source_point_name} (${relation.source_point_id_nws}) → ${relation.target_point_name} (${relation.target_point_id_nws})`, records: pairRows});
      }
      return relations;
    }

    function renderChoices(relations, preferredKey) {
      choices.replaceChildren();
      for (const relation of relations) {
        const button = doc.createElement('button');
        button.type = 'button';
        button.textContent = `${relation.label} · ${relation.records.length}`;
        button.setAttribute('aria-pressed', String(relation.key === preferredKey));
        button.className = relation.key === preferredKey ? 'active' : '';
        button.addEventListener('click', () => {
          selectedRecordId = '';
          preferredRelationKey = relation.key;
          renderRelation(relation, relations);
        });
        choices.appendChild(button);
      }
    }

    function dateLabel(row) {
      const date = unavailable(row.event_date);
      return row.date_precision === 'month' ? `${date} (month only)` : date;
    }

    function provenance(row) {
      return `${unavailable(row.source_workbook)} / ${unavailable(row.source_worksheet)} / row ${unavailable(row.source_row)} · ${row.record_id}`;
    }

    function dateSemantics(row) {
      return row.event_date_semantics === 'legacy_column_date_not_confirmed_as_crest_day'
        ? 'source date label, not confirmed as crest day'
        : 'source date meaning not independently verified';
    }

    function pointDescription(relation, row) {
      const limitations = Array.isArray(row.quality_limitations) ? row.quality_limitations.join(', ') : '';
      if (relation.kind === 'map') {
        const tc = Number.isFinite(row.tc_hours_confirmed)
          ? `verified TC ${row.tc_hours_confirmed} hours${row.tc_raw === null || row.tc_raw === undefined ? '' : `; source TC ${row.tc_raw} ${unavailable(row.tc_units_labeled)}`}`
          : row.tc_raw === null || row.tc_raw === undefined ? 'TC unavailable' : `TC source value ${row.tc_raw} (${unavailable(row.tc_units_labeled)}; clock/units unverified)`;
        const periods = row.periods_rain_raw === null || row.periods_rain_raw === undefined ? 'rainfall periods unavailable' : `rainfall periods source value ${row.periods_rain_raw}`;
        return `${dateLabel(row)} (${dateSemantics(row)}); legacy study MAP ${row.map_inches} inches; recorded crest ${row.crest_feet} feet; ${tc}; ${periods}; Tier ${row.quality_tier}; ${provenance(row)}${limitations ? `; ${limitations}` : ''}`;
      }
      const lag = Number.isFinite(row.lag_hours_confirmed)
        ? `verified crest lag ${row.lag_hours_confirmed} hours${row.lag_raw === null || row.lag_raw === undefined ? '' : `; source lag ${row.lag_raw} ${unavailable(row.lag_units_labeled)}`}`
        : row.lag_raw === null || row.lag_raw === undefined ? 'lag unavailable' : `lag source value ${row.lag_raw} (${unavailable(row.lag_units_labeled)}; units unverified)`;
      return `${dateLabel(row)} (${dateSemantics(row)}); ${relation.source_point_name} (${relation.source_point_id_nws}) source crest ${row.source_crest_feet} feet; ${relation.target_point_name} (${relation.target_point_id_nws}) target crest ${row.target_crest_feet} feet; ${lag}; Tier ${row.quality_tier}; ${provenance(row)}${limitations ? `; ${limitations}` : ''}`;
    }

    function coordinates(relation) {
      return relation.kind === 'map'
        ? {x: row => number(row.map_inches), y: row => number(row.crest_feet), xLabel: 'Historical study MAP (inches)', yLabel: 'Recorded river crest (feet)'}
        : {x: row => number(row.source_crest_feet), y: row => number(row.target_crest_feet), xLabel: `Source crest · ${relation.source_point_name} (${relation.source_point_id_nws}) · feet`, yLabel: `Target crest · ${relation.target_point_name} (${relation.target_point_id_nws}) · feet`};
    }

    function formatTick(value) {
      if (!Number.isFinite(value)) return '';
      return Number(value.toFixed(2)).toString();
    }

    function axisText(svg, x, y, text, options = {}) {
      const node = doc.createElementNS(SVG_NS, 'text');
      node.setAttribute('x', x);
      node.setAttribute('y', y);
      if (options.transform) node.setAttribute('transform', options.transform);
      if (options.anchor) node.setAttribute('text-anchor', options.anchor);
      node.textContent = text;
      svg.appendChild(node);
      return node;
    }

    function drawChart(relation) {
      chart.replaceChildren();
      const svg = doc.createElementNS(SVG_NS, 'svg');
      svg.setAttribute('viewBox', '0 0 820 390');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', `${relation.label} historical descriptive scatterplot`);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      const titleNode = doc.createElementNS(SVG_NS, 'title');
      titleNode.textContent = `${relation.label} historical descriptive scatterplot`;
      svg.appendChild(titleNode);
      const desc = doc.createElementNS(SVG_NS, 'desc');
      desc.textContent = 'Tier B source observations only. No line of fit or forecast is shown.';
      svg.appendChild(desc);

      const {x: xOf, y: yOf, xLabel, yLabel} = coordinates(relation);
      const plotted = relation.records.map(row => ({row, x: xOf(row), y: yOf(row)})).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
      const stacks = new Map();
      for (const item of plotted) {
        const key = `${item.x}\u0000${item.y}`;
        const stack = stacks.get(key) || [];
        stack.push(item);
        stacks.set(key, stack);
      }
      for (const stack of stacks.values()) stack.forEach((item, index) => { item.stackIndex = index; item.stackSize = stack.length; });
      const left = 88, right = 790, top = 25, bottom = 322;
      const xVals = plotted.map(p => p.x), yVals = plotted.map(p => p.y);
      const expand = values => {
        let min = Math.min(...values), max = Math.max(...values);
        if (min === max) { const delta = Math.max(Math.abs(min) * 0.05, 0.5); min -= delta; max += delta; }
        else { const delta = (max - min) * 0.06; min -= delta; max += delta; }
        return [min, max];
      };
      const [xMin, xMax] = expand(xVals), [yMin, yMax] = expand(yVals);
      const scaleX = value => left + (value - xMin) / (xMax - xMin) * (right - left);
      const scaleY = value => bottom - (value - yMin) / (yMax - yMin) * (bottom - top);

      const axis = doc.createElementNS(SVG_NS, 'path');
      axis.setAttribute('d', `M${left} ${top}V${bottom}H${right}`);
      axis.setAttribute('class', 'chart-axis');
      svg.appendChild(axis);
      for (let i = 0; i <= 4; i++) {
        const tx = left + i * (right - left) / 4;
        const ty = bottom - i * (bottom - top) / 4;
        const xValue = xMin + i * (xMax - xMin) / 4;
        const yValue = yMin + i * (yMax - yMin) / 4;
        axisText(svg, tx, bottom + 20, formatTick(xValue), {anchor: 'middle'});
        axisText(svg, left - 9, ty + 4, formatTick(yValue), {anchor: 'end'});
      }
      axisText(svg, (left + right) / 2, 374, xLabel, {anchor: 'middle'});
      axisText(svg, 18, (top + bottom) / 2, yLabel, {anchor: 'middle', transform: `rotate(-90 18 ${(top + bottom) / 2})`});

      for (const item of plotted) {
        const circle = doc.createElementNS(SVG_NS, 'circle');
        circle.setAttribute('cx', scaleX(item.x));
        circle.setAttribute('cy', scaleY(item.y));
        circle.setAttribute('r', item.stackSize > 1 ? String(6 + item.stackIndex * 4) : '6');
        circle.setAttribute('class', `historical-point${item.stackSize > 1 ? ' stacked' : ''}${selectedRecordId === item.row.record_id ? ' selected' : ''}`);
        circle.setAttribute('pointer-events', item.stackSize > 1 ? 'stroke' : 'all');
        circle.setAttribute('tabindex', '0');
        circle.setAttribute('role', 'button');
        circle.setAttribute('aria-label', pointDescription(relation, item.row));
        circle.dataset.recordId = item.row.record_id;
        const tip = doc.createElementNS(SVG_NS, 'title');
        tip.textContent = pointDescription(relation, item.row);
        circle.appendChild(tip);
        const selectPoint = () => {
          selectedRecordId = item.row.record_id;
          markSelection(selectedRecordId);
          drawChart(relation);
        };
        circle.addEventListener('click', selectPoint);
        circle.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectPoint(); }
        });
        svg.appendChild(circle);
      }
      chart.appendChild(svg);
    }

    function markSelection(recordId) {
      for (const row of rows.children) {
        row.className = row.dataset.recordId === recordId ? 'selected' : '';
        row.setAttribute('aria-selected', String(row.dataset.recordId === recordId));
      }
    }

    function compareRows(a, b, field) {
      const left = a[field], right = b[field];
      if (left === null || left === undefined || left === '') return right === null || right === undefined || right === '' ? 0 : 1;
      if (right === null || right === undefined || right === '') return -1;
      if (typeof left === 'number' && typeof right === 'number') return left - right;
      return String(left).localeCompare(String(right), undefined, {numeric: true});
    }

    function tableColumns(relation) {
      return relation.kind === 'map'
        ? [['event_date', 'Event date'], ['map_inches', 'MAP (inches)'], ['crest_feet', 'Crest (feet)'], ['tc_raw', 'TC (hours when verified; source raw otherwise)'], ['periods_rain_raw', 'Rainfall periods (raw)'], ['quality_tier', 'Quality'], ['source_ref', 'Source reference']]
        : [['event_date', 'Event date'], ['source_crest_feet', `Source crest · ${relation.source_point_id_nws} (feet)`], ['target_crest_feet', `Target crest · ${relation.target_point_id_nws} (feet)`], ['lag_raw', 'Lag (hours when verified; source raw otherwise)'], ['quality_tier', 'Quality'], ['source_ref', 'Source reference']];
    }

    function visibleValue(row, field) {
      if (field === 'event_date') return dateLabel(row);
      if (field === 'tc_raw') return Number.isFinite(row.tc_hours_confirmed) ? `${row.tc_hours_confirmed} hours (verified)` : row.tc_raw === null || row.tc_raw === undefined ? 'Unavailable' : `${row.tc_raw} (${unavailable(row.tc_units_labeled)}; unverified)`;
      if (field === 'lag_raw') return Number.isFinite(row.lag_hours_confirmed) ? `${row.lag_hours_confirmed} hours (verified)` : row.lag_raw === null || row.lag_raw === undefined ? 'Unavailable' : `${row.lag_raw} (${unavailable(row.lag_units_labeled)}; unverified)`;
      if (field === 'source_ref') return provenance(row);
      return unavailable(row[field]);
    }

    function renderTable(relation) {
      const columns = tableColumns(relation);
      head.replaceChildren();
      const header = doc.createElement('tr');
      for (const [field, label] of columns) {
        const th = doc.createElement('th');
        if (field !== 'source_ref') {
          th.dataset.sort = field;
          th.setAttribute('aria-sort', sortField === field ? (sortDirection === 1 ? 'ascending' : 'descending') : 'none');
        }
        if (field === 'source_ref') th.textContent = label;
        else {
          const button = doc.createElement('button');
          button.type = 'button'; button.textContent = label;
          button.addEventListener('click', () => {
            if (sortField === field) sortDirection *= -1;
            else { sortField = field; sortDirection = 1; }
            renderTable(relation);
          });
          th.appendChild(button);
        }
        header.appendChild(th);
      }
      head.appendChild(header);

      const ordered = [...relation.records].sort((a, b) => sortDirection * compareRows(a, b, sortField) || String(a.record_id).localeCompare(String(b.record_id)));
      rows.replaceChildren();
      for (const record of ordered) {
        const row = doc.createElement('tr');
        row.dataset.recordId = record.record_id;
        row.tabIndex = 0;
        row.setAttribute('aria-selected', String(record.record_id === selectedRecordId));
        row.className = record.record_id === selectedRecordId ? 'selected' : '';
        const choose = () => { selectedRecordId = record.record_id; markSelection(selectedRecordId); drawChart(relation); };
        row.addEventListener('click', choose);
        row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
        for (const [field] of columns) appendText(row, 'td', visibleValue(record, field));
        rows.appendChild(row);
      }
    }

    function renderRelation(relation, relations) {
      activeRelation = relation;
      preferredRelationKey = relation.key;
      sortField = 'event_date';
      sortDirection = 1;
      const dates = relation.records.map(row => row.event_date).filter(Boolean).sort();
      const coverage = dates.length ? `${dateLabel({event_date: dates[0], date_precision: relation.records[0].date_precision})} to ${dateLabel({event_date: dates[dates.length - 1], date_precision: relation.records[0].date_precision})}` : 'Date coverage unavailable';
      const countText = `${relation.records.length} historical descriptive records (Tier B)`;
      status.textContent = countText;
      status.className = 'historical-status';
      meta.textContent = `${coverage} · ${relation.kind === 'map' ? 'Historical legacy MAP is not current MRMS rainfall.' : `Directional pair ${relation.relationship_id}; source remains X and target remains Y.`}`;
      const labels = relation.kind === 'map'
        ? 'Legacy MAP in inches versus reported crest in feet; rainfall method and historical stage datum are unverified.'
        : `${relation.source_point_name} (${relation.source_point_id_nws}) source crest versus ${relation.target_point_name} (${relation.target_point_id_nws}) target crest, in feet.`;
      title.textContent = `${activePayload?.display_name || activeNwsli} · USGS ${activePayload?.usgs_site_id || activeGage} · NWS ${activeNwsli} · ${labels}`;
      renderChoices(relations, relation.key);
      drawChart(relation);
      renderTable(relation);
      exportButton.disabled = false;
    }

    async function renderForGage(usgsId) {
      const token = ++selectionToken;
      activeGage = String(usgsId || '');
      activeNwsli = '';
      activePayload = null;
      selectedRecordId = '';
      title.textContent = 'Historical analysis';
      if (!activeGage) { message('Select a river forecast point to view approved historical relationships.'); return; }
      message('Loading approved historical relationships…', 'loading');
      try {
        const crosswalk = await loadCrosswalk();
        if (token !== selectionToken) return;
        const mapping = crosswalk.find(item => String(item.usgs_site_id) === activeGage);
        if (!mapping) {
          title.textContent = 'Historical analysis';
          message('No verified historical station match for this dashboard gage. No nearby or name-based join was attempted.');
          return;
        }
        activeNwsli = mapping.nws_point_id;
        const payload = await loadPoint(activeNwsli);
        if (token !== selectionToken) return;
        activePayload = {...payload, display_name: mapping.display_name, usgs_site_id: mapping.usgs_site_id};
        const relations = availableRelations(payload);
        if (!relations.length) {
          title.textContent = `${mapping.display_name} (${mapping.nws_point_id})`;
          message('No approved historical relationships are available for this forecast point.');
          return;
        }
        const selected = relations.find(relation => relation.key === preferredRelationKey)
          || relations.find(relation => relation.kind === 'map')
          || relations[0];
        renderRelation(selected, relations);
      } catch (error) {
        if (token !== selectionToken) return;
        title.textContent = 'Historical analysis';
        message(`Could not load historical records: ${error.message}. Use Retry to try again.`, 'error');
      }
    }

    function downloadCsv() {
      if (!activeRelation) return;
      const blob = new Blob([csvForRecords(activeRelation.records, activeRelation.kind)], {type: 'text/csv;charset=utf-8'});
      const url = root.URL.createObjectURL(blob);
      const link = doc.createElement('a');
      link.href = url;
      link.download = `${activeNwsli}-${activeRelation.kind}-historical.csv`;
      doc.body.appendChild(link);
      link.click();
      link.remove();
      root.URL.revokeObjectURL(url);
    }

    exportButton.addEventListener('click', downloadCsv);
    retryButton.addEventListener('click', () => { if (activeGage) { crosswalkPromise = null; cache.delete(activeNwsli); renderForGage(activeGage); } });
    return {renderForGage, clear: () => renderForGage(''), refresh: () => renderForGage(activeGage), cache};
  }

  const api = {create, csvForRecords};
  root.HistoricalUI = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
