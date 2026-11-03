<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="orderSuccess" class="banner banner-success" role="status">
        <span>
          {{ t('restocking.orderPlaced', {
            orderNumber: orderSuccess.order_number,
            total: formatCurrency(orderSuccess.total_value, currentCurrency),
            date: formatDate(orderSuccess.expected_delivery)
          }) }}
        </span>
        <router-link to="/orders" class="banner-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="submitError" class="banner banner-error" role="alert">{{ submitError }}</div>

      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetTitle') }}</h3>
        </div>
        <div class="budget-body">
          <div class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</div>
          <input
            v-model.number="budget"
            type="range"
            min="0"
            :max="sliderMax"
            step="100"
            class="budget-slider"
            :aria-label="t('restocking.budgetSliderLabel')"
            @input="onBudgetInput"
          />
          <div class="budget-scale">
            <span>{{ formatCurrency(0, currentCurrency) }}</span>
            <span>{{ formatCurrency(sliderMax, currentCurrency) }}</span>
          </div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.budgetLabel') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.total_cost, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.remaining_budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ t('restocking.days', { count: plan.max_lead_time_days }) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header items-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ plan.items.length }})</h3>
          <button
            type="button"
            class="btn-primary"
            :disabled="plan.items.length === 0 || submitting || refreshing"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="plan.items.length === 0" class="empty-state">{{ t('restocking.noItems') }}</div>
        <div v-else class="table-container" :class="{ stale: refreshing }">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.demandGap') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in plan.items" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.demand_gap }}</td>
                <td><strong>{{ item.quantity }}</strong></td>
                <!-- Unit costs are small (e.g. 9.80); whole-dollar rounding would misstate them -->
                <td>{{ formatCurrencyWithDecimals(item.unit_cost, currentCurrency, 2) }}</td>
                <td><strong>{{ formatCurrency(item.line_total, currentCurrency) }}</strong></td>
                <td>{{ t('restocking.days', { count: item.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const SLIDER_STEP = 100
const SLIDER_MAX_ROUNDING = 500
const DEFAULT_BUDGET_SHARE = 0.4
const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentLocale, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const refreshing = ref(false)
    const submitting = ref(false)
    const submitError = ref(null)
    const orderSuccess = ref(null)

    const budget = ref(0)
    const sliderMax = ref(SLIDER_MAX_ROUNDING)
    const plan = ref({ items: [], total_cost: 0, remaining_budget: 0, max_lead_time_days: 0 })

    let debounceTimer = null
    // Monotonic counter: only the response of the latest request may update the plan
    let requestCounter = 0

    const fetchPlan = async () => {
      const requestId = ++requestCounter
      refreshing.value = true
      try {
        const data = await api.getRestockingRecommendations(budget.value)
        if (requestId !== requestCounter) return // stale response, a newer request is in flight
        plan.value = data
        error.value = null
      } catch (err) {
        if (requestId !== requestCounter) return
        error.value = t('restocking.loadFailed') + ': ' + err.message
      } finally {
        if (requestId === requestCounter) refreshing.value = false
      }
    }

    const onBudgetInput = () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(fetchPlan, DEBOUNCE_MS)
    }

    const initialize = async () => {
      loading.value = true
      try {
        // Learn the cost of funding every item by asking with a budget far above any
        // realistic total (the backend is greedy, so a huge budget returns all items
        // and full_cost). This sets the slider max.
        const probe = await api.getRestockingRecommendations(1e9)
        const maxBudget = Math.max(
          SLIDER_MAX_ROUNDING,
          Math.ceil(probe.full_cost / SLIDER_MAX_ROUNDING) * SLIDER_MAX_ROUNDING
        )
        sliderMax.value = maxBudget
        budget.value = Math.round((maxBudget * DEFAULT_BUDGET_SHARE) / SLIDER_STEP) * SLIDER_STEP

        // Cancel pending slider work, then load the plan for the default budget
        clearTimeout(debounceTimer)
        await fetchPlan()
      } catch (err) {
        error.value = t('restocking.loadFailed') + ': ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      if (plan.value.items.length === 0 || submitting.value) return
      submitting.value = true
      submitError.value = null
      orderSuccess.value = null
      try {
        // Only SKUs and quantities are sent; the server prices the order itself
        const payload = {
          budget: budget.value,
          items: plan.value.items.map(i => ({ sku: i.sku, quantity: i.quantity }))
        }
        orderSuccess.value = await api.createRestockingOrder(payload)
        clearTimeout(debounceTimer)
        await fetchPlan()
      } catch (err) {
        submitError.value = err.response?.data?.detail || t('restocking.orderFailed')
        console.error('Place order error:', err)
      } finally {
        submitting.value = false
      }
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return ''
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    onMounted(initialize)
    onBeforeUnmount(() => clearTimeout(debounceTimer))

    return {
      t,
      currentCurrency,
      translateProductName,
      formatCurrency,
      formatCurrencyWithDecimals,
      formatDate,
      loading,
      error,
      refreshing,
      submitting,
      submitError,
      orderSuccess,
      budget,
      sliderMax,
      plan,
      onBudgetInput,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-body {
  padding: 0 1.5rem 1.5rem;
}

.budget-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.items-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  background: #cbd5e1;
  color: #64748b;
  cursor: not-allowed;
}

.stale {
  opacity: 0.6;
  transition: opacity 0.15s;
}

.empty-state {
  padding: 2rem 1.5rem;
  text-align: center;
  color: #64748b;
}

.banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1.25rem;
  margin-bottom: 1.5rem;
  border-radius: 8px;
  font-size: 0.875rem;
}

.banner-success {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
}

.banner-error {
  background: #fee2e2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}

.banner-link {
  color: inherit;
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}
</style>
