<template>
  <div class="overflow-hidden rounded-lg border border-outline-gray-1">
    <div v-if="!days.length" class="p-6 text-center text-sm text-ink-gray-5">
      {{ __('No recorded activity in the last 7 days.') }}
    </div>
    <section v-for="day in days" :key="day.date" :aria-label="day.date">
      <div
        class="flex justify-between gap-2 border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs"
      >
        <span>{{ day.date }}</span
        ><span class="text-ink-gray-5"
          >{{ day.total ?? day.events.length }} {{ __('events') }}</span
        >
      </div>
      <div v-if="!day.events.length" class="px-4 py-3 text-xs text-ink-gray-5">
        {{
          day.total
            ? __('Events for this day are on another page.')
            : __('No recorded activity')
        }}
      </div>
      <details
        v-for="event in day.events"
        :key="event.id"
        class="group border-b border-outline-gray-1 last:border-b-0"
      >
        <summary
          class="activity-row cursor-pointer px-4 py-3 text-xs focus-visible:focus-ring"
        >
          <span class="tabular-nums text-ink-gray-5">{{
            activityTime(event.timestamp, timezone)
          }}</span>
          <component
            :is="icons[event.kind] || icons[event.category] || StepsIcon"
            class="size-4 text-ink-gray-6"
            aria-hidden="true"
          />
          <span class="truncate font-medium text-ink-gray-9">{{
            event.title
          }}</span>
          <span class="activity-copy truncate text-ink-gray-5">{{
            event.summary
          }}</span>
          <span
            class="activity-chevron text-ink-gray-5 group-open:rotate-90"
            aria-hidden="true"
            >›</span
          >
        </summary>
        <div
          class="space-y-2 bg-surface-gray-1 px-4 py-3 text-xs text-ink-gray-6 sm:pl-28"
        >
          <p>
            {{ event.actor || __('Unknown actor') }} · {{ event.timestamp }} ·
            {{ timezone }}
          </p>
          <p>
            {{ __('Source') }}:
            <a
              v-if="
                sourceLink(
                  event.source_doctype,
                  event.source_name,
                  event.source_url,
                )
              "
              :href="
                sourceLink(
                  event.source_doctype,
                  event.source_name,
                  event.source_url,
                )
              "
              class="text-ink-blue-6 hover:underline"
              >{{ event.source_doctype }} · {{ event.source_name }}</a
            ><span v-else
              >{{ event.source_doctype }} · {{ event.source_name }}</span
            >
          </p>
          <p class="whitespace-pre-wrap break-words">{{ event.summary }}</p>
          <dl v-if="detailEntries(event.details).length" class="space-y-1">
            <div
              v-for="[label, value] in detailEntries(event.details)"
              :key="label"
              class="flex flex-wrap gap-x-2"
            >
              <dt class="capitalize text-ink-gray-9">{{ label }}:</dt>
              <dd class="whitespace-pre-wrap break-words">{{ value }}</dd>
            </div>
          </dl>
          <RouterLink
            v-if="recordRoute(event.parent_doctype, event.parent_name)"
            :to="recordRoute(event.parent_doctype, event.parent_name)"
            class="inline-block text-ink-blue-6 hover:underline"
            >{{ __('Open') }} {{ event.parent_doctype }} ·
            {{ event.parent_name }} →</RouterLink
          >
        </div>
      </details>
    </section>
  </div>
</template>
<script setup>
import { RouterLink } from 'vue-router'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import InboundCallIcon from '@/components/Icons/InboundCallIcon.vue'
import OutboundCallIcon from '@/components/Icons/OutboundCallIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import EmailIcon from '@/components/Icons/EmailIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import StepsIcon from '@/components/Icons/StepsIcon.vue'
import {
  activityTime,
  detailEntries,
  recordRoute,
  sourceLink,
} from '@/utils/performance'
defineProps({
  days: { type: Array, default: () => [] },
  timezone: { type: String, required: true },
})
const icons = {
  call: PhoneIcon,
  incoming_call: InboundCallIcon,
  outgoing_call: OutboundCallIcon,
  note: NoteIcon,
  task: TaskIcon,
  task_created: TaskIcon,
  task_completed: TaskIcon,
  communication: EmailIcon,
  email: EmailIcon,
  comment: CommentIcon,
  change: StepsIcon,
  changed: StepsIcon,
  version: StepsIcon,
}
</script>
<style scoped>
.activity-row {
  display: grid;
  grid-template-columns: 48px 20px minmax(0, 1fr) 12px;
  align-items: center;
  gap: 8px;
  list-style: none;
}
.activity-row::-webkit-details-marker {
  display: none;
}
.activity-copy {
  grid-column: 3;
  grid-row: 2;
}
.activity-chevron {
  grid-column: 4;
  grid-row: 1;
}
@media (min-width: 768px) {
  .activity-row {
    grid-template-columns: 54px 24px 180px minmax(0, 1fr) 12px;
  }
  .activity-copy {
    grid-column: auto;
    grid-row: auto;
  }
  .activity-chevron {
    grid-column: auto;
    grid-row: auto;
  }
}
</style>
