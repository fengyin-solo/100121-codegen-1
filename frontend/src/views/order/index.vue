<template>
  <section class="page" data-module="order">
    <header class="page-head">
      <div>
        <h2>运输委托管理</h2>
        <p class="page-desc">围绕委托编号登记托运需求，托运状态按 待受理 → 已受理 → 运输中 依次流转；改温层要求或装载方量须先退回待受理并写明原因，全程留痕可回溯。</p>
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
          <th>流转操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '委托编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <span v-else :class="{ 'status-closed': column === '托运状态' && row[column] === '已关闭' }">
              {{ row[column] ?? '—' }}
            </span>
          </td>
          <td class="row-actions">
            <template v-for="action in availableActions(row)" :key="action.key">
              <button class="link" type="button" @click="handleAction(action.key, row)">{{ action.label }}</button>
            </template>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <span v-if="!availableActions(row).length && row['托运状态'] === '已关闭'" class="muted-text">
              已关闭，不可改动
            </span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无运输委托数据，可先登记运输委托单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条运输委托记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 登记弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3 class="modal-title">登记运输委托单</h3>
        <p class="modal-hint">带 <em class="req-mark">*</em> 为必填项；同一委托编号不能重复登记。</p>
        <div class="form-grid">
          <label v-for="field in createFields" :key="field.name" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="req-mark">*</em></span>
            <input v-model="createForm[field.name]" :placeholder="`请输入${field.label}`" />
          </label>
        </div>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">保存登记</button>
        </div>
      </div>
    </div>

    <!-- 退回原因弹窗 -->
    <div v-if="showReturn" class="modal-mask" @click.self="cancelReturn">
      <div class="modal">
        <h3 class="modal-title">退回待受理</h3>
        <p class="modal-hint">委托编号：{{ returnTarget?.['委托编号'] }}；退回后需重新受理，请写清退回原因。</p>
        <label class="form-item">
          <span>退回原因<em class="req-mark">*</em></span>
          <textarea v-model="returnReason" rows="3" placeholder="例如：委托方要求调整温层要求，需重新核定装载方案"></textarea>
        </label>
        <p v-if="returnError" class="error-text">{{ returnError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="cancelReturn">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="confirmReturn">确认退回</button>
        </div>
      </div>
    </div>

    <!-- 委托详情抽屉 -->
    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-wide">
        <div class="detail-head">
          <h3 class="modal-title">委托详情 · {{ detail['委托编号'] }}</h3>
          <span class="status-tag" :class="statusClass(detail['托运状态'])">{{ detail['托运状态'] }}</span>
        </div>
        <p class="modal-hint">
          最近处理：{{ detail['最近经办人'] || '—' }} 于 {{ detail['最近处理时间'] || '—' }}
        </p>

        <div class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-cell">
            <span class="detail-label">{{ field }}</span>
            <strong>{{ detail[field] || '—' }}</strong>
          </div>
        </div>

        <div v-if="detail['托运状态'] !== '已关闭'" class="detail-actions">
          <button
            v-if="detail['托运状态'] === '待受理'"
            class="btn primary"
            type="button"
            :disabled="submitting"
            @click="detailAction('受理委托')"
          >受理委托</button>
          <button
            v-if="detail['托运状态'] === '已受理'"
            class="btn primary"
            type="button"
            :disabled="submitting"
            @click="detailAction('开始运输')"
          >开始运输</button>
          <button
            v-if="detail['托运状态'] === '已受理' || detail['托运状态'] === '运输中'"
            class="btn"
            type="button"
            @click="openReturn(detail)"
          >退回待受理</button>
          <button class="btn ghost danger" type="button" :disabled="submitting" @click="closeOrder">关闭委托</button>
        </div>
        <p v-else class="closed-banner">该委托已关闭，资料与状态均不能再改动。</p>

        <section v-if="detail['托运状态'] === '待受理'" class="edit-block">
          <h4 class="block-title">变更委托资料</h4>
          <p class="modal-hint">当前为待受理状态，可直接修改；保存后会在流转记录中留痕。</p>
          <div class="form-grid">
            <label v-for="field in editableFields" :key="field" class="form-item">
              <span>{{ field }}</span>
              <input v-model="editForm[field]" />
            </label>
          </div>
          <p v-if="editError" class="error-text">{{ editError }}</p>
          <div class="modal-foot">
            <button class="btn primary" type="button" :disabled="submitting" @click="submitEdit">保存变更</button>
          </div>
        </section>
        <section v-else-if="detail['托运状态'] !== '已关闭'" class="edit-block">
          <h4 class="block-title">变更委托资料</h4>
          <p class="modal-hint">
            当前托运状态为「{{ detail['托运状态'] }}」，资料已锁定；如需修改
            <strong>温层要求</strong> 或 <strong>装载方量</strong>，请先点「退回待受理」并写明原因。
          </p>
        </section>

        <section class="history-block">
          <h4 class="block-title">流转记录（时间 · 经办人 · 处理动作）</h4>
          <table class="data-table history-table">
            <thead>
              <tr><th>时间</th><th>经办人</th><th>动作</th><th>状态变化</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="(record, idx) in historyRows" :key="idx">
                <td>{{ record['时间'] }}</td>
                <td>{{ record['经办人'] }}</td>
                <td>{{ record['动作'] }}</td>
                <td>{{ record['原状态'] }} → {{ record['新状态'] }}</td>
                <td>
                  <span v-if="record['退回原因']">原因：{{ record['退回原因'] }}</span>
                  <ul v-if="record['字段变更']?.length" class="change-list">
                    <li v-for="c in record['字段变更']" :key="c['字段']">
                      {{ c['字段'] }}：{{ c['原值'] }} → {{ c['新值'] }}
                    </li>
                  </ul>
                </td>
              </tr>
              <tr v-if="!historyRows.length">
                <td colspan="5" class="empty-state">暂无流转记录</td>
              </tr>
            </tbody>
          </table>
        </section>

        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null | HistoryRecord[] | undefined>
interface HistoryRecord {
  时间: string
  经办人: string
  动作: string
  原状态: string
  新状态: string
  退回原因?: string
  字段变更?: Array<{ 字段: string; 原值: string; 新值: string }>
}
interface ActionDef {
  key: string
  label: string
}

const ENDPOINT = '/api/order'
const session = useSessionStore()

const columns = ['委托编号', '委托方', '货物品名', '温层要求', '装载方量', '托运状态', '最近经办人', '最近处理时间']
const detailFields = ['委托编号', '委托方', '起运地址', '到达地址', '货物品名', '温层要求', '装载方量', '托运状态']
const editableFields = ['委托方', '起运地址', '到达地址', '货物品名', '温层要求', '装载方量']
const createFields = [
  { name: '委托编号', label: '委托编号', required: true },
  { name: '委托方', label: '委托方', required: true },
  { name: '起运地址', label: '起运地址', required: true },
  { name: '货物品名', label: '货物品名', required: true },
  { name: '到达地址', label: '到达地址', required: false },
  { name: '温层要求', label: '温层要求', required: false },
  { name: '装载方量', label: '装载方量', required: false },
]
const statuses = ['待受理', '已受理', '运输中', '已关闭']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const submitting = ref(false)

const showCreate = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>(Object.fromEntries(createFields.map((f) => [f.name, ''])))

const showReturn = ref(false)
const returnTarget = ref<Row | null>(null)
const returnReason = ref('')
const returnError = ref('')

const detail = ref<Row | null>(null)
const editForm = reactive<Record<string, string>>({})
const editError = ref('')

const stats = computed(() => {
  const count = (s: string) => rows.value.filter((r) => r['托运状态'] === s).length
  return [
    { label: '待受理委托', value: count('待受理') },
    { label: '已受理委托', value: count('已受理') },
    { label: '运输中委托', value: count('运输中') },
    { label: '已关闭委托', value: count('已关闭') },
  ]
})

const historyRows = computed<HistoryRecord[]>(() => {
  const records = (detail.value?.['流转记录'] as HistoryRecord[] | undefined) ?? []
  // 最新记录在前，接手人刷新后第一眼看到上一步是谁处理的。
  return [...records].reverse()
})

function availableActions(row: Row): ActionDef[] {
  switch (row['托运状态']) {
    case '待受理':
      return [{ key: '受理委托', label: '受理' }]
    case '已受理':
      return [
        { key: '开始运输', label: '开始运输' },
        { key: '退回待受理', label: '退回' },
      ]
    case '运输中':
      return [{ key: '退回待受理', label: '退回' }]
    default:
      return []
  }
}

function statusClass(status: unknown): string {
  return {
    待受理: 'status-pending',
    已受理: 'status-accepted',
    运输中: 'status-transit',
    已关闭: 'status-closed',
  }[String(status)] ?? ''
}

function flashSuccess(message: string) {
  successMessage.value = message
  errorMessage.value = ''
  window.setTimeout(() => {
    if (successMessage.value === message) successMessage.value = ''
  }, 4000)
}

function flashError(message: string) {
  errorMessage.value = message
  successMessage.value = ''
}

async function readResult(response: Response): Promise<{ ok: boolean; message: string; entry?: Row }> {
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload) {
    return { ok: false, message: '运输委托操作未生效，请稍后重试' }
  }
  return payload as { ok: boolean; message: string; entry?: Row }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---- 登记 ----
function openCreate() {
  createError.value = ''
  createFields.forEach((f) => { createForm[f.name] = '' })
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
}

async function submitCreate() {
  createError.value = ''
  submitting.value = true
  try {
    const values: Record<string, string> = { ...createForm, operator: session.operator }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      createError.value = result.message
      return
    }
    showCreate.value = false
    flashSuccess(result.message)
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '运输委托登记失败'
  } finally {
    submitting.value = false
  }
}

// ---- 列表动作 ----
function handleAction(action: string, row: Row) {
  if (action === '退回待受理') {
    openReturn(row)
    return
  }
  void executeAction(row, action)
}

function openReturn(row: Row) {
  returnTarget.value = row
  returnReason.value = ''
  returnError.value = ''
  showReturn.value = true
}

function cancelReturn() {
  showReturn.value = false
  returnTarget.value = null
}

async function confirmReturn() {
  if (!returnTarget.value) return
  returnError.value = ''
  if (!returnReason.value.trim()) {
    returnError.value = '退回待受理必须写清退回原因'
    return
  }
  const target = returnTarget.value
  submitting.value = true
  try {
    const updated = await postAction(target, '退回待受理', returnReason.value.trim())
    if (updated) {
      showReturn.value = false
      returnTarget.value = null
    }
  } finally {
    submitting.value = false
  }
}

async function postAction(row: Row, action: string, reason = ''): Promise<boolean> {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, reason, operator: session.operator } }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      flashError(result.message)
      return false
    }
    flashSuccess(result.message)
    await reload()
    if (detail.value && String(detail.value.id) === String(row.id) && result.entry) {
      detail.value = result.entry
    }
    return true
  } catch (error) {
    flashError(error instanceof Error ? error.message : '运输委托操作失败')
    return false
  }
}

async function executeAction(row: Row, action: string) {
  submitting.value = true
  try {
    await postAction(row, action)
  } finally {
    submitting.value = false
  }
}

async function closeOrder() {
  if (!detail.value) return
  if (!window.confirm(`确认关闭委托「${detail.value['委托编号']}」？关闭后将不能再做任何改动。`)) return
  submitting.value = true
  try {
    await postAction(detail.value, '关闭委托')
    // 详情保持打开：刷新后仍展示已关闭终态与关闭留痕，动作按钮随之消失
  } finally {
    submitting.value = false
  }
}

async function detailAction(action: string) {
  if (!detail.value) return
  submitting.value = true
  try {
    await postAction(detail.value, action)
  } finally {
    submitting.value = false
  }
}

// ---- 详情与资料变更 ----
async function openDetail(row: Row) {
  editError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      flashError('委托详情读取失败，请稍后重试')
      return
    }
    detail.value = (await response.json()) as Row
    editableFields.forEach((f) => {
      editForm[f] = String(detail.value?.[f] ?? '')
    })
  } catch (error) {
    flashError(error instanceof Error ? error.message : '委托详情读取失败')
  }
}

function closeDetail() {
  detail.value = null
}

async function submitEdit() {
  if (!detail.value) return
  editError.value = ''
  // 必填项在前端先挡一道，后端仍会复核，错误信息会明确缺的是哪一项。
  const emptyRequired = ['委托方', '起运地址', '货物品名'].filter((f) => !editForm[f]?.trim())
  if (emptyRequired.length) {
    editError.value = `缺少必填字段：${emptyRequired.join('、')}，请补全后再保存`
    return
  }
  submitting.value = true
  try {
    const values: Record<string, string> = { ...editForm, operator: session.operator }
    const response = await request(`${ENDPOINT}/${detail.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ values }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      editError.value = result.message
      return
    }
    flashSuccess(result.message)
    await reload()
    if (result.entry) detail.value = result.entry
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '委托资料变更失败'
  } finally {
    submitting.value = false
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
    flashError(error instanceof Error ? error.message : '运输委托列表读取失败')
  }
}

onMounted(reload)
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.success-text { color: #157347; }
.req-mark { color: #b42318; font-style: normal; margin-left: 2px; }

.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 40px 16px; z-index: 50; overflow-y: auto;
}
.modal {
  background: #fff; border-radius: 10px; padding: 20px 22px;
  width: 520px; max-width: 100%; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
}
.modal-wide { width: 880px; }
.modal-title { margin: 0; font-size: 16px; }
.modal-hint { color: var(--muted); font-size: 12px; margin: 6px 0 12px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-item input, .form-item textarea, .form-item select, .filter-item input, .filter-item select {
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; color: #1f2937;
}
.form-item textarea { resize: vertical; }

.detail-head { display: flex; align-items: center; justify-content: space-between; }
.status-tag { border-radius: 999px; padding: 2px 12px; font-size: 12px; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-accepted { background: #dbeafe; color: #1e40af; }
.status-transit { background: #dcfce7; color: #166534; }
.status-closed { background: #f1f5f9; color: #64748b; }

.detail-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 8px 0 14px; }
.detail-cell { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
.detail-label { display: block; color: var(--muted); font-size: 11px; margin-bottom: 4px; }
.detail-cell strong { font-size: 13px; word-break: break-all; }

.detail-actions { display: flex; gap: 8px; margin: 6px 0 4px; }
.btn.danger { color: #b42318; }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.closed-banner { margin: 8px 0; padding: 8px 12px; background: #f1f5f9; border-radius: 6px; color: #475569; font-size: 13px; }

.edit-block, .history-block { border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px; }
.block-title { margin: 0 0 8px; font-size: 14px; }
.history-table td { vertical-align: top; }
.change-list { margin: 4px 0 0; padding-left: 16px; }
</style>
