<template>
  <Dialog
    :modelValue="true"
    :title="__('Edit forecast')"
    size="sm"
    :dismissible="!saving"
    :showCloseButton="!saving"
    @update:modelValue="close"
  >
    <template #default>
      <form class="space-y-4" @submit.prevent="save">
        <p class="text-sm text-ink-gray-5">{{ deal.title || deal.name }}</p>
        <label class="block space-y-2 text-sm"
          ><span>{{ __('Expected MRR (USD / month)') }}</span
          ><input
            v-model="amount"
            aria-label="Expected MRR (USD / month)"
            type="number"
            min="0"
            step="0.01"
            required
            :disabled="saving"
            class="w-full rounded border border-outline-gray-2 bg-surface-base px-3 py-2"
        /></label>
        <label class="block space-y-2 text-sm"
          ><span>{{ __('Probability (%)') }}</span
          ><input
            v-model="probability"
            aria-label="Probability (%)"
            type="number"
            min="0"
            max="100"
            step="0.1"
            required
            :disabled="saving"
            class="w-full rounded border border-outline-gray-2 bg-surface-base px-3 py-2"
        /></label>
        <label class="block space-y-2 text-sm"
          ><span>{{ __('Expected closing month') }}</span
          ><input
            v-model="month"
            aria-label="Expected closing month"
            type="month"
            required
            :disabled="saving"
            class="w-full rounded border border-outline-gray-2 bg-surface-base px-3 py-2"
        /></label>
        <p class="text-xs text-ink-gray-5">
          {{
            __(
              'Forecast = expected MRR × probability. This does not change actual revenue or attainment.',
            )
          }}
        </p>
        <p v-if="error" role="alert" class="text-sm text-ink-red-6">
          {{ error }}
        </p>
      </form>
    </template>
    <template #actions
      ><div class="flex justify-end gap-2">
        <CRMButton :disabled="saving" @click="close">{{
          __('Cancel')
        }}</CRMButton
        ><CRMButton variant="solid" :loading="saving" @click="save">{{
          __('Save forecast')
        }}</CRMButton>
      </div></template
    >
  </Dialog>
</template>
<script setup>
import { ref } from 'vue'
import { call, Dialog, Button as CRMButton } from 'frappe-ui'
const props = defineProps({ deal: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])
const amount = ref(props.deal.expected_mrr ?? '')
const probability = ref(props.deal.probability ?? '')
const month = ref(props.deal.expected_close_month?.slice(0, 7) || '')
const saving = ref(false)
const error = ref('')
function close() {
  if (!saving.value) emit('close')
}
async function save() {
  if (saving.value) return
  error.value = ''
  const mrr = Number(amount.value),
    chance = Number(probability.value)
  if (
    amount.value === '' ||
    probability.value === '' ||
    !Number.isFinite(mrr) ||
    mrr < 0 ||
    !Number.isFinite(chance) ||
    chance < 0 ||
    chance > 100 ||
    !/^\d{4}-(0[1-9]|1[0-2])$/.test(month.value)
  ) {
    error.value = __(
      'Enter a nonnegative MRR, probability from 0 to 100, and closing month.',
    )
    return
  }
  saving.value = true
  try {
    await call('crm.api.performance.update_forecast', {
      deal: props.deal.name,
      expected_mrr: mrr,
      probability: chance,
      closing_month: month.value + '-01',
      modified: props.deal.modified,
    })
    emit('saved')
  } catch (err) {
    error.value = err.message || __('Unable to save forecast.')
  } finally {
    saving.value = false
  }
}
</script>
