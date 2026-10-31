'use strict';

let D = null, tab = 'stable';
const amounts = {};
const defaults = { BTC: 0.1, ETH: 1, SOL: 10, USDT: 10000, USDC: 10000 };
const exchanges = ['Binance', 'OKX', 'Bybit', 'Bitget', 'Gate'];
const beijing = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});
const escapeHTML = value => String(value).replace(/[&<>"']/g, char =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const formatTime = value => value && Number.isFinite(Date.parse(value))
  ? beijing.format(new Date(value)) : '暂无成功采集';

function blend(product, amount) {
  if (amount <= 0) return 0;
  let earnings = 0;
  if (product.tiers) {
    let remaining = amount;
    for (const [low, high, rate] of product.tiers) {
      const quantity = Math.max(0, Math.min(amount, high) - low);
      earnings += quantity * rate / 100;
      remaining -= quantity;
    }
    if (remaining > 0 && product.tiers.length) {
      earnings += remaining * product.tiers[product.tiers.length - 1][2] / 100;
    }
  } else {
    earnings = amount * product.base / 100;
    for (const [low, high, rate] of product.bonus) {
      earnings += Math.max(0, Math.min(amount, high) - low) * rate / 100;
    }
  }
  return earnings / amount * 100;
}

function formatNumber(value) {
  return value >= 100 ? value.toFixed(2) : value >= 1 ? value.toFixed(4) : value.toPrecision(4);
}

function updateAge() {
  if (!D) return;
  const timestamp = Date.parse(D.updated_at);
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  document.getElementById('age').textContent = Number.isFinite(timestamp)
    ? `数据更新于 ${minutes} 分钟前` : '尚无成功采集的数据';
  document.getElementById('up').textContent = formatTime(D.updated_at);
  document.getElementById('health').classList.toggle('stale',
    !Number.isFinite(timestamp) || minutes > 120 || Object.values(D.status).some(s => !s.ok));
}

function staleBadge(exchange) {
  const state = D.status[exchange];
  return state && !state.ok
    ? `<span class="tag stale">旧数据 · ${escapeHTML(formatTime(state.updated_at))} 北京时间</span>` : '';
}

function render() {
  if (!D) return;
  updateAge();
  const includeNewcomer = document.getElementById('nu').checked;
  document.getElementById('st').textContent = Object.entries(D.status)
    .filter(([, state]) => !state.ok)
    .map(([exchange, state]) => `⚠ ${exchange} 采集失败：${state.error}。` +
      (state.stale ? `保留 ${formatTime(state.updated_at)}（北京时间）的旧数据。` : '暂无可用历史数据。'))
    .join('\n');
  const coins = tab === 'stable' ? D.stable : tab === 'major' ? D.major : [...D.stable, ...D.major];
  let best = '', cards = '';
  for (const coin of coins) {
    const amount = amounts[coin] ?? defaults[coin] ?? 1000;
    const byExchange = {};
    for (const product of D.products.filter(p => p.coin === coin && (includeNewcomer || !p.newuser))) {
      const candidate = { ...product, rate: blend(product, amount) };
      if (!byExchange[product.ex] || candidate.rate > byExchange[product.ex].rate) {
        byExchange[product.ex] = candidate;
      }
    }
    const products = Object.values(byExchange).sort((a, b) => b.rate - a.rate);
    if (!products.length) continue;
    const winner = products[0];
    const maximum = winner.rate || 1;
    const missing = exchanges.filter(exchange => !byExchange[exchange]);
    const safeCoin = escapeHTML(coin);
    best += `<div class="best"><b>${safeCoin}</b> <span class="muted">${amount} ${safeCoin}</span><br>
      <span class="o">${escapeHTML(winner.ex)}</span> <span class="g">${winner.rate.toFixed(3)}%</span>
      ${staleBadge(winner.ex)}<br><span class="muted">日 ≈ ${formatNumber(amount * winner.rate / 36500)} ·
      年 ≈ ${formatNumber(amount * winner.rate / 100)} ${safeCoin}${products[1]
        ? ` · 次选 ${escapeHTML(products[1].ex)} ${products[1].rate.toFixed(3)}% ${staleBadge(products[1].ex)}` : ''}</span></div>`;
    cards += `<div class="box" data-coin="${safeCoin}"><div class="coin-head"><b>${safeCoin}</b>
      <label class="muted">金额 <input type="number" min="0" step="any" aria-label="${safeCoin} 金额"
        data-amount="${safeCoin}" value="${amount}"> ${safeCoin}</label></div>`;
    cards += products.map((product, index) => `<div class="row"><div class="rate-row">
      <b>${index + 1}. ${escapeHTML(product.ex)}</b><div class="track"><div class="fill"
        style="width:${product.rate / maximum * 100}%"></div></div>
      <span class="g" style="font-size:15px">${product.rate.toFixed(3)}%</span></div>
      ${staleBadge(product.ex)} <span class="tag">${escapeHTML(product.type)}</span>
      <span class="muted">日收益 ≈ ${formatNumber(amount * product.rate / 36500)} ·
      年收益 ≈ ${formatNumber(amount * product.rate / 100)} ${safeCoin} · 采用：${escapeHTML(product.name)}</span>
      <details><summary>详情 · 分档 · 来源</summary>${product.tiers
        ? product.tiers.map(t => `${t[0]}–${t[1]}：${t[2]}%`).join('<br>')
        : `基础 ${product.base.toFixed(3)}%` + product.bonus.map(t =>
          `<br>+ ${t[0]}–${t[1]} 档额外 ${t[2].toFixed(2)}%`).join('')}
      <br>来源：${escapeHTML(product.source)}</details></div>`).join('');
    cards += (missing.length ? `<div class="muted">无活期产品/不可用：${missing.join('、')}</div>` : '') + '</div>';
  }
  document.getElementById('best').innerHTML = best || '<p class="muted">当前筛选暂无可用产品。</p>';
  document.getElementById('cards').innerHTML = cards;
}

async function load() {
  try {
    const response = await fetch('./data/rates.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Snapshot request failed');
    const snapshot = await response.json();
    if (!Array.isArray(snapshot.products) || !Array.isArray(snapshot.stable)
        || !Array.isArray(snapshot.major) || !snapshot.status) throw new Error('Invalid snapshot');
    D = snapshot;
    render();
  } catch (error) {
    document.getElementById('st').textContent = '数据文件加载失败，请稍后刷新。' +
      (D ? '当前保留页面已加载的数据。' : '');
    document.getElementById('health').classList.add('stale');
    if (!D) document.getElementById('age').textContent = '数据加载失败';
  }
}

document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {
  tab = button.dataset.t;
  document.querySelectorAll('.tab').forEach(other => {
    const selected = other === button;
    other.classList.toggle('on', selected);
    other.setAttribute('aria-pressed', String(selected));
  });
  render();
}));
document.getElementById('nu').addEventListener('change', render);
document.getElementById('cards').addEventListener('change', event => {
  const coin = event.target.dataset.amount;
  if (!coin) return;
  const amount = event.target.valueAsNumber;
  if (!Number.isFinite(amount) || amount < 0) {
    event.target.setCustomValidity('请输入大于或等于 0 的金额');
    event.target.reportValidity();
    return;
  }
  event.target.setCustomValidity('');
  amounts[coin] = amount;
  render();
});
load();
setInterval(load, 60000);
setInterval(updateAge, 30000);
