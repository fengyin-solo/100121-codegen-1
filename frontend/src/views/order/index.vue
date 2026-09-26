<template>
  <section class="page" data-module="order">
    <header class="page-head">
      <div>
        <h2>运输委托管理</h2>
        <p class="page-desc">托运状态按待受理 → 已受理 → 运输中 → 已关闭依次流转；温层要求、装载方量须退回待受理后才能改，每次变更都记下时间与经办人。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记运输委托单</button>
        <button class="btn" type="button" @click="exportRows">导出运输委托清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>委托编号</span>
        <input v-model="keyword" placeholder="按委托编号检索" />
      </label>
      <label class="filter-item">
        <span>托运状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>上一步经办</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '托运状态'" class="status-tag" :data-status="row[column]">{{ row[column] ?? '—' }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>{{ lastOperator(row) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-if="!isClosed(row)">
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="onAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="openEdit(row)">修改</button>
            </template>
            <span v-else class="closed-hint">已关闭，不可改动</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无运输委托数据，可先登记运输委托单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条运输委托记录 · 当前经办：{{ session.operator }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <!-- 登记运输委托单 -->
    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-card">
        <h3>登记运输委托单</h3>
        <form @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.name" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
            <input v-model="createForm[field.name]" :placeholder="field.placeholder" />
          </label>
          <p class="form-operator">经办人：{{ session.operator }}</p>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">保存登记</button>
            <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 修改委托内容 -->
    <div v-if="editTarget" class="modal-mask" @click.self="editTarget = null">
      <div class="modal-card">
        <h3>修改委托 {{ editTarget['委托编号'] }}</h3>
        <p v-if="editTarget['托运状态'] !== '待受理'" class="guard-hint">
          当前状态为「{{ editTarget['托运状态'] }}」：温层要求、装载方量须先退回待受理并写清原因后才能修改。
        </p>
        <form @submit.prevent="submitEdit">
          <label v-for="field in editFields" :key="field" class="form-item">
            <span>{{ field }}<em v-if="guardedFields.includes(field)" class="guard-mark">（关键约定）</em></span>
            <input v-model="editForm[field]" />
          </label>
          <p class="form-operator">经办人：{{ session.operator }}</p>
          <p v-if="editError" class="error-text">{{ editError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">保存修改</button>
            <button class="btn ghost" type="button" @click="editTarget = null">取消</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 退回待受理 -->
    <div v-if="returnTarget" class="modal-mask" @click.self="returnTarget = null">
      <div class="modal-card">
        <h3>退回待受理 · {{ returnTarget['委托编号'] }}</h3>
        <form @submit.prevent="submitReturn">
          <label class="form-item">
            <span>退回原因<em class="required-mark">*</em></span>
            <textarea v-model="returnReason" rows="3" placeholder="写清退回原因，例如：温层约定需调整"></textarea>
          </label>
          <p class="form-operator">经办人：{{ session.operator }}</p>
          <p v-if="returnError" class="error-text">{{ returnError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">确认退回</button>
            <button class="btn ghost" type="button" @click="returnTarget = null">取消</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 委托详情 + 流转记录 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-card wide">
        <h3>委托详情 · {{ detail['委托编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>
              <span v-if="column === '托运状态'" class="status-tag" :data-status="detail[column]">{{ detail[column] ?? '—' }}</span>
              <template v-else>{{ detail[column] ?? '—' }}</template>
            </dd>
          </template>
        </dl>
        <h4>流转记录</h4>
        <ol class="history-list">
          <li v-for="(item, index) in detail['流转记录'] ?? []" :key="index">
            <span class="history-time">{{ item['时间'] }}</span>
            <strong>{{ item['动作'] }}</strong>
            <span class="history-operator">经办人：{{ item['经办人'] }}</span>
            <span class="history-detail">{{ item['说明'] }}</span>
          </li>
        </ol>
        <div class="modal-actions">
          <button class="btn" type="button" @click="refreshDetail">刷新</button>
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, any>

const ENDPOINT = '/api/order'
const columns = ["委托编号", "委托方", "起运地址", "到达地址", "货物品名", "温层要求", "装载方量", "托运状态"]
const statuses = ["待受理", "已受理", "运输中", "已关闭"]
const guardedFields = ["温层要求", "装载方量"]
const editFields = ["委托方", "起运地址", "到达地址", "货物品名", "温层要求", "装载方量"]
const createFields = [
  { name: '委托编号', label: '委托编号', required: true, placeholder: '如 ORDE-0005' },
  { name: '委托方', label: '委托方', required: true, placeholder: '委托方名称' },
  { name: '起运地址', label: '起运地址', required: true, placeholder: '装货地址' },
  { name: '到达地址', label: '到达地址', required: true, placeholder: '卸货地址' },
  { name: '货物品名', label: '货物品名', required: true, placeholder: '如 冷冻牛肉' },
  { name: '温层要求', label: '温层要求', required: false, placeholder: '如 冷冻 -18℃' },
  { name: '装载方量', label: '装载方量', required: false, placeholder: '如 28方' },
]
// 每个状态下允许执行的正向动作；退回待受理在已受理、运输中都可用
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待受理: ['受理委托'],
  已受理: ['开始运输', '退回待受理'],
  运输中: ['关闭委托', '退回待受理'],
}

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')

const editTarget = ref<Row | null>(null)
const editForm = ref<Record<string, string>>({})
const editError = ref('')

const returnTarget = ref<Row | null>(null)
const returnReason = ref('')
const returnError = ref('')

const detail = ref<Row | null>(null)

const stats = computed(() =>
  statuses.map((s) => ({
    label: `${s}委托`,
    value: rows.value.filter((row) => row['托运状态'] === s).length,
  })),
)

function isClosed(row: Row) {
  return row['托运状态'] === '已关闭'
}

function availableActions(row: Row) {
  return ACTIONS_BY_STATUS[String(row['托运状态'])] ?? []
}

function lastOperator(row: Row) {
  const history = row['流转记录'] ?? []
  const last = history[history.length - 1]
  return last ? `${last['经办人']} · ${last['动作']}` : '—'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

function openEdit(row: Row) {
  editTarget.value = row
  editForm.value = Object.fromEntries(editFields.map((field) => [field, String(row[field] ?? '')]))
  editError.value = ''
}

async function parseResult(response: Response) {
  const payload = await response.json()
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message ?? payload.detail ?? '操作未生效')
  }
  return payload
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, operator: session.operator } }),
    })
    const payload = await parseResult(response)
    createVisible.value = false
    noticeMessage.value = payload.message ?? '运输委托单已登记'
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记失败'
  }
}

async function submitEdit() {
  if (!editTarget.value) return
  editError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${editTarget.value.id}/update`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...editForm.value, operator: session.operator } }),
    })
    const payload = await parseResult(response)
    editTarget.value = null
    noticeMessage.value = payload.message ?? '运输委托单已更新'
    await reload()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '修改失败'
  }
}

async function runAction(action: string, row: Row, reason = '') {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: session.operator, reason } }),
    })
    const payload = await parseResult(response)
    noticeMessage.value = payload.message ?? `运输委托单已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运输委托操作失败'
  }
}

function onAction(action: string, row: Row) {
  if (action === '退回待受理') {
    returnTarget.value = row
    returnReason.value = ''
    returnError.value = ''
    return
  }
  void runAction(action, row)
}

async function submitReturn() {
  if (!returnTarget.value) return
  returnError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${returnTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action: '退回待受理', operator: session.operator, reason: returnReason.value.trim() },
      }),
    })
    const payload = await parseResult(response)
    returnTarget.value = null
    noticeMessage.value = payload.message ?? '运输委托单已退回待受理'
    await reload()
  } catch (error) {
    returnError.value = error instanceof Error ? error.message : '退回失败'
  }
}

async function openDetail(row: Row) {
  detail.value = null
  const response = await request(`${ENDPOINT}/${row.id}`)
  if (!response.ok) {
    errorMessage.value = '委托详情读取失败'
    return
  }
  detail.value = await response.json()
}

async function refreshDetail() {
  if (!detail.value) return
  const response = await request(`${ENDPOINT}/${detail.value.id}`)
  if (response.ok) {
    detail.value = await response.json()
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('运输委托单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运输委托列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #eef2f7; }
.status-tag[data-status='待受理'] { background: #fff4e0; color: #9a6a00; }
.status-tag[data-status='已受理'] { background: #e3efff; color: #1f6feb; }
.status-tag[data-status='运输中'] { background: #e6f7ec; color: #157347; }
.status-tag[data-status='已关闭'] { background: #eceff3; color: #64748b; }
.closed-hint { color: var(--muted); font-size: 12px; }
.notice-text { color: #157347; }
.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.35);
  display: flex; align-items: center; justify-content: center; z-index: 20;
}
.modal-card {
  background: #fff; border-radius: 10px; padding: 18px 20px; width: 420px; max-width: 92vw;
  max-height: 86vh; overflow: auto; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.modal-card.wide { width: 560px; }
.modal-card h3 { margin: 0 0 12px; font-size: 15px; }
.modal-card h4 { margin: 14px 0 8px; font-size: 13px; }
.form-item { display: block; margin-bottom: 10px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input, .form-item textarea, .filter-item select {
  width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px;
}
.filter-item select { width: auto; min-width: 120px; }
.required-mark { color: #b42318; font-style: normal; margin-left: 2px; }
.guard-mark { color: #9a6a00; font-style: normal; font-size: 11px; }
.guard-hint { background: #fff4e0; border-radius: 6px; padding: 8px 10px; font-size: 12px; color: #9a6a00; }
.form-operator { font-size: 12px; color: var(--muted); }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.detail-grid { display: grid; grid-template-columns: 96px 1fr 96px 1fr; gap: 6px 10px; margin: 0; font-size: 13px; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.history-list { margin: 0; padding-left: 18px; font-size: 13px; display: flex; flex-direction: column; gap: 8px; }
.history-time { color: var(--muted); margin-right: 8px; }
.history-operator { margin: 0 8px; color: #1f6feb; }
.history-detail { color: var(--muted); }
</style>
