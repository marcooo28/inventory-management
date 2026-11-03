<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'view' ? t('dashboard.purchaseOrder.viewTitle') : t('dashboard.purchaseOrder.createTitle') }}
            </h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <!-- Backlog item context (both modes) -->
            <div class="context-card">
              <div class="info-item">
                <div class="info-label">{{ t('dashboard.purchaseOrder.orderId') }}</div>
                <div class="info-value mono">{{ backlogItem.order_id }}</div>
              </div>
              <div class="info-item">
                <div class="info-label">{{ t('dashboard.purchaseOrder.sku') }}</div>
                <div class="info-value mono">{{ backlogItem.item_sku }}</div>
              </div>
              <div class="info-item">
                <div class="info-label">{{ t('dashboard.purchaseOrder.itemName') }}</div>
                <div class="info-value">{{ translateProductName(backlogItem.item_name) }}</div>
              </div>
              <div class="info-item">
                <div class="info-label">{{ t('dashboard.purchaseOrder.shortage') }}</div>
                <div class="info-value danger">{{ shortage }} {{ t('dashboard.purchaseOrder.units') }}</div>
              </div>
            </div>

            <!-- View mode -->
            <template v-if="mode === 'view'">
              <div v-if="loading" class="state-message">{{ t('dashboard.purchaseOrder.loading') }}</div>
              <div v-else-if="loadError" class="error-banner">{{ loadError }}</div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.poId') }}</div>
                  <div class="info-value mono">{{ purchaseOrder.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.status') }}</div>
                  <div class="info-value"><span class="badge">{{ purchaseOrder.status }}</span></div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.supplierName') }}</div>
                  <div class="info-value">{{ purchaseOrder.supplier_name }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.quantity') }}</div>
                  <div class="info-value">{{ purchaseOrder.quantity }} {{ t('dashboard.purchaseOrder.units') }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.unitCost') }}</div>
                  <div class="info-value">{{ formatUsd(purchaseOrder.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.total') }}</div>
                  <div class="info-value strong">{{ formatUsd(purchaseOrder.quantity * purchaseOrder.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.expectedDelivery') }}</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.expected_delivery_date) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.createdDate') }}</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.created_date) }}</div>
                </div>
                <div class="info-item full-width">
                  <div class="info-label">{{ t('dashboard.purchaseOrder.notes') }}</div>
                  <div class="info-value notes">{{ purchaseOrder.notes || t('dashboard.purchaseOrder.noNotes') }}</div>
                </div>
              </div>
            </template>

            <!-- Create mode -->
            <form v-else id="po-form" class="po-form" novalidate @submit.prevent="submit">
              <div v-if="submitError" class="error-banner">{{ submitError }}</div>

              <div class="form-field full-width">
                <label for="po-supplier">{{ t('dashboard.purchaseOrder.supplierName') }}</label>
                <input id="po-supplier" v-model="form.supplier_name" type="text" maxlength="200" :class="{ invalid: errors.supplier_name }" />
                <div v-if="errors.supplier_name" class="field-error">{{ errors.supplier_name }}</div>
              </div>

              <div class="form-field">
                <label for="po-quantity">{{ t('dashboard.purchaseOrder.quantity') }}</label>
                <input id="po-quantity" v-model="form.quantity" type="number" min="1" step="1" :class="{ invalid: errors.quantity }" />
                <div v-if="errors.quantity" class="field-error">{{ errors.quantity }}</div>
              </div>

              <div class="form-field">
                <label for="po-unit-cost">{{ t('dashboard.purchaseOrder.unitCost') }}</label>
                <input id="po-unit-cost" v-model="form.unit_cost" type="number" min="0" step="0.01" :class="{ invalid: errors.unit_cost }" />
                <div v-if="errors.unit_cost" class="field-error">{{ errors.unit_cost }}</div>
              </div>

              <div class="form-field full-width">
                <label for="po-date">{{ t('dashboard.purchaseOrder.expectedDelivery') }}</label>
                <input id="po-date" v-model="form.expected_delivery_date" type="date" :min="today" :class="{ invalid: errors.expected_delivery_date }" />
                <div v-if="errors.expected_delivery_date" class="field-error">{{ errors.expected_delivery_date }}</div>
              </div>

              <div class="form-field full-width">
                <label for="po-notes">{{ t('dashboard.purchaseOrder.notes') }}</label>
                <textarea id="po-notes" v-model="form.notes" rows="3" maxlength="1000" :class="{ invalid: errors.notes }"></textarea>
                <div v-if="errors.notes" class="field-error">{{ errors.notes }}</div>
              </div>

              <div class="total-row full-width">
                <span class="info-label">{{ t('dashboard.purchaseOrder.total') }}</span>
                <span class="total-value">{{ formatUsd(total) }}</span>
              </div>
            </form>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn-secondary" @click="close">{{ t('common.close') }}</button>
            <button
              v-if="mode === 'create'"
              type="submit"
              form="po-form"
              class="btn-primary"
              :disabled="saving"
            >
              {{ saving ? t('dashboard.purchaseOrder.saving') : t('dashboard.purchaseOrder.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const { t, translateProductName, currentLocale } = useI18n()

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  backlogItem: { type: Object, default: null },
  mode: { type: String, default: 'create', validator: (v) => ['create', 'view'].includes(v) }
})

const emit = defineEmits(['close', 'po-created'])

const form = reactive({
  supplier_name: '',
  quantity: 1,
  unit_cost: '',
  expected_delivery_date: '',
  notes: ''
})
const errors = reactive({})
const saving = ref(false)
const submitError = ref('')

const purchaseOrder = ref(null)
const loading = ref(false)
const loadError = ref('')

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

// Local-time YYYY-MM-DD (toISOString would shift the day for non-UTC users)
const today = computed(() => {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
})

const total = computed(() => {
  const q = Number(form.quantity)
  const c = Number(form.unit_cost)
  return Number.isFinite(q) && Number.isFinite(c) && q > 0 && c > 0 ? q * c : 0
})

// PO amounts are stored in USD by the backend, so they are always shown in USD
// (not converted by the locale-based currency helper).
const formatUsd = (amount) =>
  Number(amount || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' })

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return dateString
  return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
    year: 'numeric', month: 'long', day: 'numeric'
  })
}

const close = () => emit('close')

const resetForm = () => {
  form.supplier_name = ''
  // Default to covering exactly the shortage (never below 1)
  form.quantity = Math.max(1, shortage.value)
  form.unit_cost = ''
  form.expected_delivery_date = ''
  form.notes = ''
  Object.keys(errors).forEach((k) => delete errors[k])
  submitError.value = ''
  saving.value = false
}

// Client-side validation mirroring the backend (PurchaseOrderCreate)
const validate = () => {
  Object.keys(errors).forEach((k) => delete errors[k])
  const name = form.supplier_name.trim()
  if (!name) errors.supplier_name = t('dashboard.purchaseOrder.errSupplierRequired')
  else if (name.length > 200) errors.supplier_name = t('dashboard.purchaseOrder.errSupplierLength')

  const qty = Number(form.quantity)
  if (form.quantity === '' || !Number.isInteger(qty) || qty <= 0) {
    errors.quantity = t('dashboard.purchaseOrder.errQuantity')
  }

  const cost = Number(form.unit_cost)
  if (form.unit_cost === '' || !Number.isFinite(cost) || cost <= 0) {
    errors.unit_cost = t('dashboard.purchaseOrder.errUnitCost')
  }

  const date = new Date(form.expected_delivery_date)
  if (!form.expected_delivery_date || isNaN(date.getTime())) {
    errors.expected_delivery_date = t('dashboard.purchaseOrder.errDate')
  } else if (form.expected_delivery_date < today.value) {
    // ISO date strings compare correctly as plain strings
    errors.expected_delivery_date = t('dashboard.purchaseOrder.errDatePast')
  }

  if (form.notes.length > 1000) errors.notes = t('dashboard.purchaseOrder.errNotes')
  return Object.keys(errors).length === 0
}

// FastAPI returns detail as a string (404/409) or a list of {loc, msg} (422)
const extractApiError = (err, fallback) => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : ''
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('; ')
  }
  return fallback
}

const submit = async () => {
  if (saving.value || !validate()) return
  saving.value = true
  submitError.value = ''
  try {
    const payload = {
      backlog_item_id: props.backlogItem.id,
      supplier_name: form.supplier_name.trim(),
      quantity: Number(form.quantity),
      unit_cost: Number(form.unit_cost),
      expected_delivery_date: form.expected_delivery_date
    }
    const notes = form.notes.trim()
    if (notes) payload.notes = notes
    const po = await api.createPurchaseOrder(payload)
    emit('po-created', po)
  } catch (err) {
    console.error('Create PO error:', err)
    submitError.value = extractApiError(err, t('dashboard.purchaseOrder.saveFailed'))
  } finally {
    saving.value = false
  }
}

const loadPurchaseOrder = async () => {
  loading.value = true
  loadError.value = ''
  purchaseOrder.value = null
  try {
    purchaseOrder.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    console.error('Load PO error:', err)
    loadError.value = extractApiError(err, t('dashboard.purchaseOrder.loadFailed'))
  } finally {
    loading.value = false
  }
}

// Reset / fetch every time the modal opens (or the item/mode changes while open)
watch(
  () => [props.isOpen, props.backlogItem?.id, props.mode],
  () => {
    if (!props.isOpen || !props.backlogItem) return
    if (props.mode === 'view') loadPurchaseOrder()
    else resetForm()
  },
  { immediate: true }
)
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 640px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.context-card {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem 1.5rem;
  padding: 1.25rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  margin-bottom: 1.5rem;
}

.info-grid,
.po-form {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem 1.5rem;
}

.full-width {
  grid-column: 1 / -1;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}

.info-label,
.form-field label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.info-value.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.info-value.danger {
  color: #dc2626;
  font-weight: 700;
}

.info-value.strong {
  font-weight: 700;
}

.info-value.notes {
  white-space: pre-wrap;
  font-weight: 400;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.625rem;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
  background: #dbeafe;
  color: #1e40af;
  text-transform: capitalize;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-field input,
.form-field textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.938rem;
  font-family: inherit;
  color: #0f172a;
  background: white;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.form-field textarea {
  resize: vertical;
}

.form-field input:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.form-field input.invalid,
.form-field textarea.invalid {
  border-color: #ef4444;
}

.field-error {
  font-size: 0.813rem;
  color: #dc2626;
}

.error-banner {
  grid-column: 1 / -1;
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.state-message {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
}

.total-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.total-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary,
.btn-primary {
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #334155;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  background: #0f172a;
  border: 1px solid #0f172a;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 560px) {
  .context-card,
  .info-grid,
  .po-form {
    grid-template-columns: 1fr;
  }
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
