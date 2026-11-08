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

  function niceTicks(minimum, maximum, target = 8) {
    let min = Number(minimum), max = Number(maximum);
    if (!Number.isFinite(min) || !Number.isFinite(max)) { min = -1; max = 1; }
    if (min > max) [min, max] = [max, min];
    target = Math.max(3, Math.min(12, Math.round(Number(target) || 8)));
    let span = max - min;
    if (span === 0) {
      span = Math.max(0.5, Math.abs(min) * 0.05);
      min -= span / 2;
      max += span / 2;
    }
    const rawStep = span / (target - 1);
    const power = 10 ** Math.floor(Math.log10(rawStep));
    const factor = [1, 2, 2.5, 5, 10].find(value => value * power >= rawStep) || 10;
    const step = factor * power;
    const precision = Math.min(12, Math.max(0, Math.ceil(-Math.log10(step)) + (factor === 2.5 ? 1 : 0)));
    const round = value => Number(value.toFixed(precision));
    const lower = Math.floor(min / step + 1e-10) * step;
    const upper = Math.ceil(max / step - 1e-10) * step;
    const ticks = [];
    for (let value = lower, index = 0; value <= upper + step * 1e-8 && index < 40; value += step, index++) ticks.push(round(value));
    return {min: round(lower), max: round(upper), step: round(step), ticks};
  }

  function csvForRecords(records, kind) {
    const fields = kind === 'map'
      ? ['record_id', 'event_date', 'date_precision', 'map_inches', 'crest_feet', 'tc_raw', 'tc_units_labeled', 'tc_hours_confirmed', 'periods_rain_raw', 'quality_tier', 'source_workbook', 'source_worksheet', 'source_row', 'source_file_sha256', 'source_class', 'qpe_product', 'validation_status', 'crest_time_utc', 'rain_start_utc', 'rain_end_utc', 'source_url']
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
    let visibleRelation = null;
    let sourceChoice = 'legacy';
    let approvedEvents = [];
    let approvedPromise = null;
    let sortField = 'event_date';
    let sortDirection = 1;
    let selectedRecordId = '';
    let preferredRelationKey = '';

    const status = $('hist-status');
    const title = $('hist-title');
    const meta = $('hist-meta');
    const choices = $('hist-relationships');
    const chart = $('hist-chart');
    const sourceChoices = $('hist-source-choices');
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
      if (sourceChoices) sourceChoices.replaceChildren();
      chart.replaceChildren();
      head.replaceChildren();
      rows.replaceChildren();
      meta.textContent = '';
      activeRelation = null;
      visibleRelation = null;
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


    // Reconstruction remains invisible until scientific review explicitly approves
    // individual events. Provisional stage/QPE outputs are never promoted by the UI.
    async function loadApprovedEvents() {
      if (!sourceChoices) return [];
      if (!approvedPromise) {
        approvedPromise = fetcher(options.reconstructionUrl || 'reconstruction/results/pilot_events.json')
          .then(async response => {
            if (!response.ok) return [];
            const payload = await response.json();
            if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.events)) return [];
            return payload.events.filter(event =>
              event.validation_status === 'SCIENCE_APPROVED' &&
              ['AMIL1', 'MNLM6'].includes(event.nwsli) &&
              Number.isFinite(event.map_inches) && Number.isFinite(event.crest_feet) &&
              typeof event.crest_time_utc === 'string' &&
              typeof event.rain_start_utc === 'string' && typeof event.rain_end_utc === 'string' &&
              typeof event.qpe_product === 'string' && event.qpe_product.length > 0
            );
          }).catch(() => []);
      }
      return approvedPromise;
    }

    function approvedRows(nwsli) {
      return approvedEvents.filter(event => event.nwsli === nwsli).map(event => ({
        ...event,
        record_id: 'reconstruction:' + String(event.event_id),
        event_date: event.crest_time_utc.slice(0, 10),
        date_precision: 'day',
        quality_tier: 'APPROVED',
        source_class: 'independent_reconstruction',
        source_workbook: null,
        source_worksheet: null,
        source_row: null,
        source_file_sha256: null,
      }));
    }

    function renderSourceChoices(relation, relations) {
      if (!sourceChoices) return;
      sourceChoices.replaceChildren();
      if (relation.kind !== 'map' || !['AMIL1', 'MNLM6'].includes(activeNwsli)) return;
      const available = approvedRows(activeNwsli).length > 0;
      if (!available) sourceChoice = 'legacy';
      const label = doc.createElement('span');
      label.textContent = 'MAP–crest source: ';
      sourceChoices.appendChild(label);
      for (const [key, text] of [['legacy', 'Legacy'], ['reconstructed', 'Reconstructed'], ['both', 'Both']]) {
        const button = doc.createElement('button');
        button.type = 'button';
        button.textContent = text;
        button.disabled = key !== 'legacy' && !available;
        button.className = sourceChoice === key ? 'active' : '';
        button.setAttribute('aria-pressed', String(sourceChoice === key));
        if (button.disabled) button.title = 'No independently reconstructed, science-approved events have been published.';
        button.addEventListener('click', () => {
          if (button.disabled) return;
          sourceChoice = key;
          selectedRecordId = '';
          renderRelation(relation, relations);
        });
        sourceChoices.appendChild(button);
      }
      if (!available) {
        const note = doc.createElement('span');
        note.textContent = ' Reconstructed events pending independent scientific verification.';
        sourceChoices.appendChild(note);
      }
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
      if (relation.kind === 'map' && row.source_class === 'independent_reconstruction') {
        return `${row.event_date}; independent ${row.qpe_product} MAP ${row.map_inches.toFixed(2)} inches; observed crest ${row.crest_feet.toFixed(2)} feet at ${row.crest_time_utc}; rainfall window ${row.rain_start_utc} to ${row.rain_end_utc}; ${row.validation_status}; ${unavailable(row.source_url)}`;
      }
      if (relation.kind === 'map') {
        const tc = Number.isFinite(row.tc_hours_confirmed)
          ? `verified TC ${row.tc_hours_confirmed} hours${row.tc_raw === null || row.tc_raw === undefined ? '' : `; source TC ${row.tc_raw} ${unavailable(row.tc_units_labeled)}`}`
          : row.tc_raw === null || row.tc_raw === undefined ? 'TC unavailable' : `TC source value ${row.tc_raw} (${unavailable(row.tc_units_labeled)}; clock/units unverified)`;
        const periods = row.periods_rain_raw === null || row.periods_rain_raw === undefined ? 'rainfall periods unavailable' : `rainfall periods source value ${row.periods_rain_raw}`;
        return `${dateLabel(row)} (${dateSemantics(row)}); legacy study MAP ${row.map_inches.toFixed(2)} inches; recorded crest ${row.crest_feet.toFixed(2)} feet; ${tc}; ${periods}; Tier ${row.quality_tier}; ${provenance(row)}${limitations ? `; ${limitations}` : ''}`;
      }
      const lag = Number.isFinite(row.lag_hours_confirmed)
        ? `verified crest lag ${row.lag_hours_confirmed} hours${row.lag_raw === null || row.lag_raw === undefined ? '' : `; source lag ${row.lag_raw} ${unavailable(row.lag_units_labeled)}`}`
        : row.lag_raw === null || row.lag_raw === undefined ? 'lag unavailable' : `lag source value ${row.lag_raw} (${unavailable(row.lag_units_labeled)}; units unverified)`;
      return `${dateLabel(row)} (${dateSemantics(row)}); ${relation.source_point_name} (${relation.source_point_id_nws}) source crest ${row.source_crest_feet} feet; ${relation.target_point_name} (${relation.target_point_id_nws}) target crest ${row.target_crest_feet} feet; ${lag}; Tier ${row.quality_tier}; ${provenance(row)}${limitations ? `; ${limitations}` : ''}`;
    }

    function coordinates(relation) {
      return relation.kind === 'map'
        ? {x: row => number(row.map_inches), y: row => number(row.crest_feet), xLabel: 'Mean Areal Precipitation (inches)', yLabel: 'Observed River Crest (feet)'}
        : {x: row => number(row.source_crest_feet), y: row => number(row.target_crest_feet), xLabel: `Source crest · ${relation.source_point_name} (${relation.source_point_id_nws}) · feet`, yLabel: `Target crest · ${relation.target_point_name} (${relation.target_point_id_nws}) · feet`};
    }

    function formatTick(value, step = 1) {
      if (!Number.isFinite(value)) return '';
      const decimals = step < 1 ? Math.min(6, Math.max(1, Math.ceil(-Math.log10(step)) + 1e-9)) : 0;
      return Number(value.toFixed(decimals)).toString();
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
      svg.setAttribute('viewBox', '0 0 900 490');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', `${relation.label} historical descriptive scatterplot`);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      const titleNode = doc.createElementNS(SVG_NS, 'title');
      titleNode.textContent = `${relation.label} historical descriptive scatterplot`;
      svg.appendChild(titleNode);
      const desc = doc.createElementNS(SVG_NS, 'desc');
      desc.textContent = 'Source observations only. No line of fit or forecast is shown. Focus or hover a point to show its values and crosshairs; select it to keep the guides and synchronize the event table.';
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
      const left = 98, right = 874, top = 30, bottom = 386;
      const xVals = plotted.map(p => p.x), yVals = plotted.map(p => p.y);
      const tickTarget = Math.max(4, Math.min(10, Math.floor((chart.clientWidth || 760) / 85)));
      const xAxis = niceTicks(Math.min(...xVals), Math.max(...xVals), tickTarget);
      const yAxis = niceTicks(Math.min(...yVals), Math.max(...yVals), Math.min(10, tickTarget + 1));
      const {min: xMin, max: xMax} = xAxis, {min: yMin, max: yMax} = yAxis;
      const scaleX = value => left + (value - xMin) / (xMax - xMin) * (right - left);
      const scaleY = value => bottom - (value - yMin) / (yMax - yMin) * (bottom - top);

      for (const value of xAxis.ticks) {
        const line = doc.createElementNS(SVG_NS, 'line');
        const x = scaleX(value);
        line.setAttribute('x1', x); line.setAttribute('x2', x);
        line.setAttribute('y1', top); line.setAttribute('y2', bottom);
        line.setAttribute('class', 'chart-grid chart-grid-vertical'); line.dataset.tickValue = String(value);
        svg.appendChild(line);
        const tick = doc.createElementNS(SVG_NS, 'line');
        tick.setAttribute('x1', x); tick.setAttribute('x2', x); tick.setAttribute('y1', bottom); tick.setAttribute('y2', bottom + 6);
        tick.setAttribute('class', 'chart-tick'); svg.appendChild(tick);
        axisText(svg, x, bottom + 22, formatTick(value, xAxis.step), {anchor: 'middle'});
      }
      for (const value of yAxis.ticks) {
        const line = doc.createElementNS(SVG_NS, 'line');
        const y = scaleY(value);
        line.setAttribute('x1', left); line.setAttribute('x2', right);
        line.setAttribute('y1', y); line.setAttribute('y2', y);
        line.setAttribute('class', 'chart-grid chart-grid-horizontal'); line.dataset.tickValue = String(value);
        svg.appendChild(line);
        const tick = doc.createElementNS(SVG_NS, 'line');
        tick.setAttribute('x1', left - 6); tick.setAttribute('x2', left); tick.setAttribute('y1', y); tick.setAttribute('y2', y);
        tick.setAttribute('class', 'chart-tick'); svg.appendChild(tick);
        axisText(svg, left - 10, y + 4, formatTick(value, yAxis.step), {anchor: 'end'});
      }

      const crosshair = doc.createElementNS(SVG_NS, 'g');
      crosshair.setAttribute('class', 'chart-crosshair-group'); crosshair.setAttribute('visibility', 'hidden');
      crosshair.setAttribute('pointer-events', 'none');
      const vertical = doc.createElementNS(SVG_NS, 'line');
      vertical.setAttribute('class', 'chart-crosshair chart-crosshair-vertical');
      vertical.setAttribute('x1', left); vertical.setAttribute('x2', left); vertical.setAttribute('y1', top); vertical.setAttribute('y2', bottom);
      const horizontal = doc.createElementNS(SVG_NS, 'line');
      horizontal.setAttribute('class', 'chart-crosshair chart-crosshair-horizontal');
      horizontal.setAttribute('x1', left); horizontal.setAttribute('x2', right); horizontal.setAttribute('y1', top); horizontal.setAttribute('y2', top);
      crosshair.appendChild(vertical); crosshair.appendChild(horizontal); svg.appendChild(crosshair);

      const tooltip = doc.createElementNS(SVG_NS, 'g');
      tooltip.setAttribute('class', 'chart-hover-tooltip'); tooltip.setAttribute('role', 'tooltip'); tooltip.setAttribute('visibility', 'hidden'); tooltip.setAttribute('pointer-events', 'none');
      const tooltipBox = doc.createElementNS(SVG_NS, 'rect'); tooltipBox.setAttribute('width', '306'); tooltipBox.setAttribute('height', '104'); tooltipBox.setAttribute('rx', '7');
      tooltipBox.setAttribute('class', 'chart-tooltip-box'); tooltip.appendChild(tooltipBox);
      const tooltipText = doc.createElementNS(SVG_NS, 'text'); tooltipText.setAttribute('x', '10'); tooltipText.setAttribute('y', '19'); tooltip.appendChild(tooltipText);

      function guidesFor(item) {
        if (!item) { crosshair.setAttribute('visibility', 'hidden'); tooltip.setAttribute('visibility', 'hidden'); return; }
        const px = scaleX(item.x), py = scaleY(item.y);
        vertical.setAttribute('x1', px); vertical.setAttribute('x2', px); vertical.setAttribute('y1', py); vertical.setAttribute('y2', bottom);
        horizontal.setAttribute('x1', left); horizontal.setAttribute('x2', px); horizontal.setAttribute('y1', py); horizontal.setAttribute('y2', py);
        crosshair.dataset.recordId = item.row.record_id; crosshair.setAttribute('visibility', 'visible');
        tooltipText.replaceChildren();
        const lines = tooltipLines(relation, item.row);
        for (const [index, line] of lines.entries()) {
          const tspan = doc.createElementNS(SVG_NS, 'tspan'); tspan.setAttribute('x', '10'); tspan.setAttribute('dy', index ? '17' : '0'); tspan.textContent = line; tooltipText.appendChild(tspan);
        }
        tooltipBox.setAttribute('height', String(12 + lines.length * 17));
        const tooltipWidth = 308, tooltipHeight = 12 + lines.length * 17;
        const tx = px > (left + right) / 2 ? Math.max(left + 2, px - tooltipWidth - 10) : Math.min(right - tooltipWidth + 2, px + 12);
        const ty = Math.max(top + 2, Math.min(bottom - tooltipHeight, py - tooltipHeight - 8));
        tooltip.setAttribute('transform', `translate(${tx} ${ty})`); tooltip.setAttribute('visibility', 'visible');
      }

      function tooltipLines(_relation, row) {
        if (_relation.kind === 'map') {
          const source = row.source_class === 'independent_reconstruction' ? `Reconstructed · ${unavailable(row.qpe_product)}` : `Legacy · ${unavailable(row.source_workbook)}`;
          const window = row.rain_start_utc && row.rain_end_utc ? `${row.rain_start_utc} – ${row.rain_end_utc}` : 'Unavailable';
          const crestTime = row.crest_time_utc || (row.source_class === 'independent_reconstruction' ? 'Unavailable' : 'Not present in date-only legacy source');
          return [`Date: ${dateLabel(row)}${row.source_class === 'independent_reconstruction' ? '' : ' (source label)'}`,
            `MAP: ${Number(row.map_inches).toFixed(2)} in · crest: ${Number(row.crest_feet).toFixed(2)} ft`,
            `${activeNwsli} · ${source}`, `Quality: ${unavailable(row.validation_status || row.quality_tier)}`,
            `Rain window: ${window}`, `Crest timestamp: ${crestTime}`,
            `Provenance: ${unavailable(row.source_url || row.source_workbook)}`];
        }
        return [pointDescription(_relation, row).slice(0, 240)];
      }

      const axis = doc.createElementNS(SVG_NS, 'path');
      axis.setAttribute('d', `M${left} ${top}V${bottom}H${right}`);
      axis.setAttribute('class', 'chart-axis');
      svg.appendChild(axis);
      axisText(svg, (left + right) / 2, 468, xLabel, {anchor: 'middle'});
      axisText(svg, 22, (top + bottom) / 2, yLabel, {anchor: 'middle', transform: `rotate(-90 22 ${(top + bottom) / 2})`});

      for (const item of plotted) {
        const circle = doc.createElementNS(SVG_NS, 'circle');
        circle.setAttribute('cx', scaleX(item.x));
        circle.setAttribute('cy', scaleY(item.y));
        circle.setAttribute('r', item.stackSize > 1 ? String(8 + item.stackIndex * 4) : '8');
        circle.setAttribute('class', `historical-point${item.row.source_class === 'independent_reconstruction' ? ' reconstructed' : ''}${item.stackSize > 1 ? ' stacked' : ''}${selectedRecordId === item.row.record_id ? ' selected' : ''}`);
        circle.setAttribute('pointer-events', item.stackSize > 1 ? 'stroke' : 'all');
        circle.setAttribute('tabindex', '0');
        circle.setAttribute('role', 'button');
        circle.setAttribute('aria-label', pointDescription(relation, item.row));
        circle.dataset.recordId = item.row.record_id;
        const tip = doc.createElementNS(SVG_NS, 'title');
        tip.textContent = pointDescription(relation, item.row);
        circle.appendChild(tip);
        const selectPoint = () => {
          selectedRecordId = selectedRecordId === item.row.record_id ? '' : item.row.record_id;
          markSelection(selectedRecordId);
          drawChart(relation);
        };
        circle.addEventListener('pointerenter', () => guidesFor(item));
        circle.addEventListener('focus', () => guidesFor(item));
        circle.addEventListener('pointerleave', () => guidesFor(selectedRecordId ? plotted.find(other => other.row.record_id === selectedRecordId) : null));
        circle.addEventListener('blur', () => guidesFor(selectedRecordId ? plotted.find(other => other.row.record_id === selectedRecordId) : null));
        circle.addEventListener('click', selectPoint);
        circle.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectPoint(); }
        });
        svg.appendChild(circle);
      }
      svg.appendChild(tooltip);
      svg.addEventListener('pointerleave', () => guidesFor(selectedRecordId ? plotted.find(item => item.row.record_id === selectedRecordId) : null));
      if (selectedRecordId) guidesFor(plotted.find(item => item.row.record_id === selectedRecordId));
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
        ? [['event_date', 'Event date'], ['map_inches', 'MAP (inches)'], ['crest_feet', 'Crest (feet)'], ['tc_raw', 'TC (hours when verified; source raw otherwise)'], ['periods_rain_raw', 'Rainfall periods (raw)'], ['quality_tier', 'Quality'], ['source_class', 'Series'], ['source_ref', 'Source reference']]
        : [['event_date', 'Event date'], ['source_crest_feet', `Source crest · ${relation.source_point_id_nws} (feet)`], ['target_crest_feet', `Target crest · ${relation.target_point_id_nws} (feet)`], ['lag_raw', 'Lag (hours when verified; source raw otherwise)'], ['quality_tier', 'Quality'], ['source_ref', 'Source reference']];
    }

    function visibleValue(row, field) {
      if (field === 'event_date') return dateLabel(row);
      if (field === 'tc_raw') return Number.isFinite(row.tc_hours_confirmed) ? `${row.tc_hours_confirmed} hours (verified)` : row.tc_raw === null || row.tc_raw === undefined ? 'Unavailable' : `${row.tc_raw} (${unavailable(row.tc_units_labeled)}; unverified)`;
      if (field === 'lag_raw') return Number.isFinite(row.lag_hours_confirmed) ? `${row.lag_hours_confirmed} hours (verified)` : row.lag_raw === null || row.lag_raw === undefined ? 'Unavailable' : `${row.lag_raw} (${unavailable(row.lag_units_labeled)}; unverified)`;
      if (field === 'source_ref') return row.source_class === 'independent_reconstruction' ? `${unavailable(row.qpe_product)} · ${unavailable(row.source_url)} · ${unavailable(row.validation_status)}` : provenance(row);
      if (field === 'source_class') return row.source_class === 'independent_reconstruction' ? 'Reconstructed' : 'Legacy';
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
        const choose = () => { selectedRecordId = selectedRecordId === record.record_id ? '' : record.record_id; markSelection(selectedRecordId); drawChart(relation); };
        row.addEventListener('click', choose);
        row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
        for (const [field] of columns) appendText(row, 'td', visibleValue(record, field));
        rows.appendChild(row);
      }
    }

    function renderRelation(relation, relations) {
      activeRelation = relation;
      preferredRelationKey = relation.key;
      renderSourceChoices(relation, relations);
      const reconstructed = relation.kind === 'map' ? approvedRows(activeNwsli) : [];
      const records = sourceChoice === 'reconstructed' ? reconstructed :
        sourceChoice === 'both' && relation.kind === 'map' ? [...relation.records, ...reconstructed] :
          relation.records;
      visibleRelation = {...relation, records};
      sortField = 'event_date';
      sortDirection = 1;
      const dates = relation.records.map(row => row.event_date).filter(Boolean).sort();
      const coverage = dates.length ? `${dateLabel({event_date: dates[0], date_precision: relation.records[0].date_precision})} to ${dateLabel({event_date: dates[dates.length - 1], date_precision: relation.records[0].date_precision})}` : 'Date coverage unavailable';
      const countText = relation.kind !== 'map' || sourceChoice === 'legacy'
        ? `${relation.records.length} historical descriptive records (Tier B)`
        : sourceChoice === 'reconstructed'
          ? `${records.length} independently reconstructed, science-approved observations`
          : `${records.length} observations · ${relation.records.length} legacy and ${reconstructed.length} science-approved reconstructed`;
      status.textContent = countText;
      status.className = 'historical-status';
      meta.textContent = `${coverage} · ${relation.kind === 'map' ? 'Historical legacy MAP is not current MRMS rainfall.' : `Directional pair ${relation.relationship_id}; source remains X and target remains Y.`}`;
      const labels = relation.kind === 'map'
        ? 'Legacy MAP in inches versus reported crest in feet; rainfall method and historical stage datum are unverified.'
        : `${relation.source_point_name} (${relation.source_point_id_nws}) source crest versus ${relation.target_point_name} (${relation.target_point_id_nws}) target crest, in feet.`;
      title.textContent = `${activePayload?.display_name || activeNwsli} · USGS ${activePayload?.usgs_site_id || activeGage} · NWS ${activeNwsli} · ${labels}`;
      renderChoices(relations, relation.key);
      drawChart(visibleRelation);
      renderTable(visibleRelation);
      exportButton.disabled = !records.length;
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
        sourceChoice = 'legacy';
        approvedEvents = ['AMIL1', 'MNLM6'].includes(activeNwsli) ? await loadApprovedEvents() : [];
        if (token !== selectionToken) return;
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
      if (!visibleRelation) return;
      const blob = new Blob([csvForRecords(visibleRelation.records, visibleRelation.kind)], {type: 'text/csv;charset=utf-8'});
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
    root.addEventListener?.('resize', () => { if (visibleRelation) drawChart(visibleRelation); });
    return {renderForGage, clear: () => renderForGage(''), refresh: () => renderForGage(activeGage), cache};
  }

  const api = {create, csvForRecords, niceTicks};
  root.HistoricalUI = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
