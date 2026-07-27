<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        <span class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
      </div>
      <input
        type="range"
        min="0"
        max="50000"
        step="500"
        v-model.number="budget"
        class="budget-slider"
      />
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="summary-bar">
        <div class="summary-item">
          <span class="summary-label">{{ t('restocking.totalCost') }}</span>
          <span class="summary-value">{{ currencySymbol }}{{ recommendations.total_cost.toLocaleString() }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('restocking.remainingBudget') }}</span>
          <span class="summary-value">{{ currencySymbol }}{{ recommendations.remaining_budget.toLocaleString() }}</span>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationsTitle') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.recommendedQuantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendations.items"
                :key="item.item_sku"
                :class="{ 'not-funded': item.recommended_quantity === 0 }"
              >
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.forecasted_demand }}</td>
                <td>
                  <strong v-if="item.recommended_quantity > 0">{{ item.recommended_quantity }}</strong>
                  <span v-else class="not-funded-label">{{ t('restocking.notFunded') }}</span>
                </td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toFixed(2) }}</td>
                <td>{{ currencySymbol }}{{ item.line_total.toLocaleString() }}</td>
                <td>{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="place-order-bar">
        <div v-if="orderConfirmation" class="order-confirmation">
          {{ t('restocking.orderSuccess', { orderNumber: orderConfirmation.order_number, date: formatDate(orderConfirmation.expected_delivery) }) }}
        </div>
        <div v-if="submitError" class="error">{{ submitError }}</div>
        <button
          class="place-order-button"
          :disabled="!canPlaceOrder || submitting"
          @click="placeOrder"
        >
          {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const budget = ref(10000)
    const loading = ref(true)
    const error = ref(null)
    const recommendations = ref({ items: [], total_cost: 0, remaining_budget: 0 })

    const submitting = ref(false)
    const submitError = ref(null)
    const orderConfirmation = ref(null)

    let debounceTimer = null
    let latestRequestId = 0

    const loadRecommendations = async () => {
      const requestId = ++latestRequestId
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockingRecommendations(budget.value)
        // Ignore this response if a newer request has already been fired
        // (guards against a slow response overwriting a fresher one).
        if (requestId === latestRequestId) {
          recommendations.value = data
        }
      } catch (err) {
        if (requestId === latestRequestId) {
          error.value = 'Failed to load recommendations: ' + err.message
        }
      } finally {
        if (requestId === latestRequestId) {
          loading.value = false
        }
      }
    }

    watch(budget, () => {
      orderConfirmation.value = null
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, 300)
    })

    const canPlaceOrder = computed(() => {
      return recommendations.value.items.some(item => item.recommended_quantity > 0)
    })

    const placeOrder = async () => {
      try {
        submitting.value = true
        submitError.value = null
        orderConfirmation.value = null

        const itemsToOrder = recommendations.value.items
          .filter(item => item.recommended_quantity > 0)
          .map(item => ({
            item_sku: item.item_sku,
            item_name: item.item_name,
            quantity: item.recommended_quantity,
            unit_cost: item.unit_cost
          }))

        const order = await api.createRestockingOrder({
          budget: budget.value,
          items: itemsToOrder
        })

        orderConfirmation.value = order
        await loadRecommendations()
      } catch (err) {
        submitError.value = 'Failed to submit order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    const formatDate = (dateString) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return new Date(dateString).toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    onMounted(loadRecommendations)
    onUnmounted(() => {
      if (debounceTimer) clearTimeout(debounceTimer)
    })

    return {
      t,
      budget,
      loading,
      error,
      recommendations,
      currencySymbol,
      translateProductName,
      canPlaceOrder,
      submitting,
      submitError,
      orderConfirmation,
      placeOrder,
      formatDate
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  margin-top: 0.5rem;
  accent-color: #2563eb;
}

.summary-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-item {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.summary-label {
  font-size: 0.813rem;
  color: #64748b;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

tr.not-funded {
  opacity: 0.5;
}

.not-funded-label {
  color: #94a3b8;
  font-style: italic;
  font-size: 0.85rem;
}

.place-order-bar {
  margin-top: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.75rem;
}

.order-confirmation {
  align-self: stretch;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
}

.place-order-button {
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-button:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
</style>
