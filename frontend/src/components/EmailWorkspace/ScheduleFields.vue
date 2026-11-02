<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7">
      {{ __('Send at') }}
      <input
        v-model="wall"
        type="datetime-local"
        class="min-w-0 rounded border border-outline-gray-2 bg-surface-gray-2 p-2 text-ink-gray-9 placeholder-ink-gray-4 [color-scheme:light] focus:border-outline-gray-4 focus:bg-surface-base focus:outline-none focus:ring-2 focus:ring-outline-gray-3 disabled:cursor-not-allowed disabled:opacity-50 dark:[color-scheme:dark]"
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
        class="min-w-0 rounded border border-outline-gray-2 bg-surface-gray-2 p-2 text-ink-gray-9 placeholder-ink-gray-4 [color-scheme:light] focus:border-outline-gray-4 focus:bg-surface-base focus:outline-none focus:ring-2 focus:ring-outline-gray-3 disabled:cursor-not-allowed disabled:opacity-50 dark:[color-scheme:dark]"
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
