<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7">
      {{ __('Send at') }}
      <input
        v-model="wall"
        type="datetime-local"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        :disabled="disabled"
      />
    </label>
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7">
      {{ __('Timezone') }}
      <input
        v-model="timezone"
        type="text"
        :list="listId"
        placeholder="Europe/London"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        :disabled="disabled"
      />
      <datalist :id="listId">
        <option v-for="zone in zones" :key="zone" :value="zone" />
      </datalist>
    </label>
  </div>
</template>
<script setup>
import { useId } from 'vue'
defineProps({ disabled: Boolean })
const wall = defineModel('wall', { type: String, default: '' })
const timezone = defineModel('timezone', { type: String, default: 'UTC' })
const listId = `email-timezones-${useId()}`
const zones = [
  ...new Set(['UTC', ...(Intl.supportedValuesOf?.('timeZone') || [])]),
]
</script>
