<template>
  <Dialog
    :modelValue="true"
    :title="__('Edit monthly target')"
    size="sm"
    :dismissible="!saving"
    :showCloseButton="!saving"
    @update:modelValue="close"
  >
    <template #default>
      <form
        id="performance-target-form"
        class="space-y-4"
        @submit.prevent="save"
      >
        <p class="text-sm text-ink-gray-5">{{ salespersonLabel }} · USD</p>
        <label class="block space-y-2 text-sm text-ink-gray-9"
          ><span>{{ __('Target month') }}</span
          ><select
            v-model="month"
            aria-label="Target month"
            class="w-full rounded border border-outline-gray-2 bg-surface-base px-3 py-2"
            :disabled="saving"
          >
            <option v-for="option in months" :key="option" :value="option">
              {{ periodLabel(option) }}
            </option>
          </select></label
        >
        <label class="block space-y-2 text-sm text-ink-gray-9"
          ><span>{{ __('Monthly new MRR target (USD)') }}</span
          ><input
            v-model="amount"
            aria-label="Monthly new MRR target (USD)"
            type="number"
            min="0"
            step="0.01"
            required
            class="w-full rounded border border-outline-gray-2 bg-surface-base px-3 py-2"
            :disabled="saving"
        /></label>
        <label class="flex items-center gap-2 text-sm text-ink-gray-9"
          ><input
            v-model="recurring"
            aria-label="Repeat for future months"
            type="checkbox"
            :disabled="saving || !canRepeat"
          />{{ __('Repeat for future months') }}</label
        >
        <p v-if="!canRepeat" class="text-xs text-ink-gray-5">
          {{
            __('Recurring targets must start in the current or a future month.')
          }}
        </p>
        <p class="text-xs text-ink-gray-5">
          {{
            recurring
              ? __('Recurring target effective from')
              : __('Updates only')
          }}
          {{ periodLabel(month) }}.
          {{ __('Existing historical monthly targets are retained.') }}
        </p>
        <p v-if="error" role="alert" class="text-sm text-ink-red-6">
          {{ error }}
        </p>
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <CRMButton :disabled="saving" @click="close">{{
          __('Cancel')
        }}</CRMButton
        ><CRMButton variant="solid" :loading="saving" @click="save">{{
          __('Save target')
        }}</CRMButton>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { call, Dialog, Button as CRMButton } from 'frappe-ui'
import { periodLabel, targetAmount } from '@/utils/performance'
const props = defineProps({
  salesperson: { type: String, required: true },
  salespersonLabel: { type: String, required: true },
  months: { type: Array, required: true },
  targets: { type: Array, default: () => [] },
  today: { type: String, required: true },
})
const emit = defineEmits(['close', 'saved'])
const month = ref(props.months[0])
const amount = ref('')
const recurring = ref(false)
const saving = ref(false)
const error = ref('')
const canRepeat = computed(() => month.value >= props.today.slice(0, 7) + '-01')
watch(
  month,
  (value) => {
    amount.value =
      props.targets.find((target) => target.month === value)?.amount ?? ''
    error.value = ''
    if (!canRepeat.value) recurring.value = false
  },
  { immediate: true },
)
function close() {
  if (!saving.value) emit('close')
}
async function save() {
  if (saving.value) return
  error.value = ''
  try {
    const value = targetAmount(amount.value)
    saving.value = true
    await call('crm.api.performance.set_target', {
      salesperson: props.salesperson,
      month: month.value,
      amount: value,
      recurring: recurring.value,
    })
    emit('saved')
  } catch (err) {
    error.value = err.message || 'Unable to save target.'
  } finally {
    saving.value = false
  }
}
</script>
