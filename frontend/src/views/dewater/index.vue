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

    <!-- 统计卡片全部取自后端 /stats，与列表、运营概览共用同一份判定口径 -->
    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'error-text': item.danger && Number(item.value) > 0 }">{{ item.display }}</strong>
      </article>
    </div>

    <form v-if="creating" class="filter-bar" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field" class="filter-item">
        <span>{{ field === '进泥量' ? '进泥量(m³)' : field }}</span>
        <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit">提交登记</button>
      <button class="btn ghost" type="button" @click="creating = false">取消</button>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="filters.keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>脱水机编号</span>
        <input v-model="filters.machine" placeholder="按脱水机编号检索" />
      </label>
      <label class="filter-item">
        <span>运行状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in meta.statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>异常说明</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-abnormal': row.abnormal }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td :class="{ 'error-text': row.abnormal }">{{ row['异常说明'] || '正常' }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRun(action, row)"
              :title="canRun(action, row) ? '' : `当前为「${row.status}」，不能重复${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">当前筛选条件下没有脱水运行记录，可调整条件或登记新记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条脱水运行记录（记录已持久保存，刷新或重启服务不会丢失）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface Meta {
  statuses: string[]
  actions: string[]
  action_targets: Record<string, string>
  action_allowed_from: Record<string, string[]>
  negative_actions: string[]
  feed_min: number
  feed_max: number
}

interface StatsData {
  total: number
  running: number
  pending: number
  abnormal: number
  feed_abnormal: number
  running_duration: number
  moisture_avg: number | null
}

const ENDPOINT = '/api/dewater'
const columns = ["记录编号", "脱水机编号", "进泥量", "出泥含水率", "絮凝剂用量", "运行时长", "操作人员", "运行状态"]
const createFields = ["记录编号", "脱水机编号", "进泥量", "出泥含水率", "絮凝剂用量", "运行时长", "操作人员"]

const fallbackMeta: Meta = {
  statuses: ["待开机", "运行中", "已停机", "故障停机"],
  actions: ["确认开机", "确认停机", "登记故障"],
  action_targets: { 确认开机: '运行中', 确认停机: '已停机', 登记故障: '故障停机' },
  action_allowed_from: { 确认开机: ['待开机'], 确认停机: ['运行中'], 登记故障: ['待开机', '运行中'] },
  negative_actions: ['登记故障'],
  feed_min: 0,
  feed_max: 200,
}

const meta = ref<Meta>(fallbackMeta)
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive({ keyword: '', machine: '', status: '' })
const creating = ref(false)
const createForm = reactive<Record<string, string>>({})

const stats = ref([
  { label: '运行机组', value: 0, display: '0', danger: false },
  { label: '待处理记录', value: 0, display: '0', danger: false },
  { label: '进泥量异常', value: 0, display: '0', danger: true },
  { label: '运行中累计时长(h)', value: 0, display: '0', danger: false },
  { label: '出泥含水率均值(%)', value: 0, display: '—', danger: false },
])

function canRun(action: string, row: Row): boolean {
  // 按钮可用性同样来自后端 meta 口径，前端不自行解释状态流转。
  return meta.value.action_allowed_from[action]?.includes(String(row.status)) ?? false
}

function applyStats(data: StatsData) {
  stats.value[0].value = data.running
  stats.value[0].display = String(data.running)
  stats.value[1].value = data.pending
  stats.value[1].display = String(data.pending)
  stats.value[2].value = data.feed_abnormal
  stats.value[2].display = String(data.feed_abnormal)
  stats.value[3].value = data.running_duration
  stats.value[3].display = String(data.running_duration)
  stats.value[4].value = data.moisture_avg ?? 0
  stats.value[4].display = data.moisture_avg === null ? '—' : String(data.moisture_avg)
}

function resetFilters() {
  filters.keyword = ''
  filters.machine = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createFields.forEach((field) => { createForm[field] = '' })
  creating.value = true
}

async function readMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.clone().json()
    if (payload && typeof payload.message === 'string') return payload.message
    if (payload && typeof payload.detail === 'string') return payload.detail
  } catch {
    // 非 JSON 响应时退回通用说明
  }
  return fallback
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '脱水记录登记失败'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水记录登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 没有记录、同机重复开停机等说明直接展示后端给出的原因，不再吞掉。
      errorMessage.value = payload.message || '脱水运行动作未生效，请稍后重试'
      await reload()
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.machine) params.set('machine', filters.machine)
  if (filters.status) params.set('status', filters.status)
  try {
    const [listRes, statsRes] = await Promise.all([
      request(`${ENDPOINT}?${params.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listRes.ok) {
      errorMessage.value = await readMessage(listRes, '脱水记录列表读取失败')
      return
    }
    const payload = await listRes.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsRes.ok) {
      applyStats(await statsRes.json() as StatsData)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行列表读取失败'
  }
}

onMounted(async () => {
  try {
    const response = await request(`${ENDPOINT}/meta`)
    if (response.ok) meta.value = await response.json() as Meta
  } catch {
    // meta 取不到时使用内置兜底口径，不阻塞列表加载
  }
  await reload()
})
</script>

<style scoped>
tr.row-abnormal td {
  background: #fef3f2;
}
.link:disabled {
  color: #9aa4b2;
  cursor: not-allowed;
}
</style>
