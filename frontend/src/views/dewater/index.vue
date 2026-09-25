<template>
  <section class="page" data-module="dewater">
    <header class="page-head">
      <div>
        <h2>脱水运行管理</h2>
        <p class="page-desc">维护脱水记录，围绕记录编号、脱水机编号、进泥量、出泥含水率做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记脱水记录</button>
        <button class="btn" type="button" @click="exportRows">导出脱水运行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-abnormal': row.abnormal }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              :class="{ danger: negativeActions.includes(action) }"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无脱水运行数据，可先登记脱水记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条脱水运行记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

type Meta = {
  columns: string[]
  statuses: string[]
  actions: string[]
  negative_actions: string[]
}

type Summary = {
  total: number
  cards: { label: string; value: number }[]
  message: string
}

type ActionPayload = {
  ok?: boolean
  message?: string
}

const ENDPOINT = '/api/dewater'
// 列、动作、统计卡片全部来自后端同一份判定口径，页面不再各自硬编码
const columns = ref<string[]>([])
const actions = ref<string[]>([])
const negativeActions = ref<string[]>([])
const stats = ref<{ label: string; value: number }[]>([])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ref<string[]>([])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '脱水记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const payload = await fetchJson<ActionPayload>(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!payload.ok) {
      // 业务拦截（记录不存在、重复开停机等）把后端说明原样亮出来
      errorMessage.value = payload.message ?? '脱水运行动作未生效，请稍后重试'
      return
    }
    noticeMessage.value = payload.message ?? '脱水运行动作已生效'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行操作失败'
  }
}

async function loadMeta() {
  const meta = await fetchJson<Meta>(`${ENDPOINT}/meta`)
  columns.value = meta.columns ?? []
  actions.value = meta.actions ?? []
  negativeActions.value = meta.negative_actions ?? []
  filterFields.value = columns.value.slice(0, 3)
}

async function loadSummary() {
  const summary = await fetchJson<Summary>(`${ENDPOINT}/summary`)
  stats.value = summary.cards ?? []
  if (summary.message) {
    noticeMessage.value = summary.message
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const payload = await fetchJson<{ items?: Row[]; total?: number }>(`${ENDPOINT}?${query}`)
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 列表与统计走同一份口径，刷新时一起更新，保证两边一致
    await loadSummary()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行列表读取失败'
  }
}

onMounted(async () => {
  try {
    await loadMeta()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行页面配置读取失败'
  }
  await reload()
})
</script>
