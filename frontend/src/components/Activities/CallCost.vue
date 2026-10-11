<template>
  <p
    v-if="cost && cost.status !== 'Excluded'"
    class="text-xs text-ink-gray-5"
    aria-label="Twilio voice cost"
  >
    {{ __('Twilio voice cost') }} · {{ formatted
    }}<span v-if="cost.status !== 'Complete'">
      · {{ __('billing pending') }}</span
    >
  </p>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { call } from 'frappe-ui'
const props = defineProps({ name: { type: String, default: '' } })
const cost = ref(null)
let request = 0
const formatted = computed(() => {
  if (cost.value?.amount == null || !cost.value.currency) return __('Pending')
  const value = Number(cost.value.amount)
  if (!Number.isFinite(value)) return __('Pending')
  return cost.value.currency === 'USD'
    ? `$${value.toFixed(4)}`
    : `${value.toFixed(4)} ${cost.value.currency}`
})
watch(
  () => props.name,
  async (name) => {
    const current = ++request
    cost.value = null
    if (!name) return
    try {
      const data = await call('crm.api.performance.get_call_cost', { name })
      if (current === request) cost.value = data
    } catch {
      if (current === request) cost.value = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => request++)
</script>
