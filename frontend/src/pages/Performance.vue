<template>
  <div
    class="flex h-full flex-col overflow-hidden bg-surface-base text-ink-gray-9"
  >
    <LayoutHeader
      ><template #left-header
        ><span class="text-sm text-ink-gray-5">CRM /</span
        ><span class="text-sm">{{ __('Performance') }}</span></template
      ></LayoutHeader
    >
    <main
      class="performance mx-auto w-full max-w-7xl flex-1 overflow-y-auto px-4 py-6 sm:px-8"
    >
      <div class="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="mb-1 text-2xl font-semibold tracking-tight">
            {{ __('Sales performance') }}
          </h1>
          <p class="text-sm text-ink-gray-5">
            {{ __('Targets, pipeline, and the work behind them.') }}
          </p>
        </div>
        <CRMButton
          v-if="context?.manager"
          :disabled="
            !summary || filters.salesperson === 'team' || summaryLoading
          "
          @click="showTarget = true"
          >{{ __('Edit target') }}</CRMButton
        >
      </div>
      <div
        v-if="contextLoading"
        role="status"
        class="py-8 text-sm text-ink-gray-5"
      >
        {{ __('Loading Performance…') }}
      </div>
      <div v-else-if="contextError" role="alert" class="space-y-3 py-8 text-sm">
        <p>{{ contextError }}</p>
        <CRMButton @click="loadContext">{{ __('Retry access') }}</CRMButton>
      </div>
      <template v-else-if="context && filters">
        <div class="mb-6 flex flex-wrap items-end gap-3">
          <label
            v-if="context.manager"
            class="grid gap-1 text-xs text-ink-gray-5"
            ><span>{{ __('Salesperson') }}</span
            ><select
              :value="filters.salesperson"
              aria-label="Salesperson"
              @change="updateFilters({ salesperson: $event.target.value })"
            >
              <option
                v-for="user in context.users"
                :key="user.name"
                :value="user.name"
              >
                {{ user.full_name || user.name }}
              </option>
              <option value="team">{{ __('Whole team') }}</option>
            </select></label
          >
          <div v-else class="grid gap-1 text-xs text-ink-gray-5">
            <span>{{ __('Salesperson') }}</span
            ><span class="py-2 text-sm text-ink-gray-9">{{
              salespersonLabel
            }}</span>
          </div>
          <div class="grid gap-1">
            <span class="text-xs text-ink-gray-5">{{ __('Period') }}</span>
            <div
              role="group"
              :aria-label="__('Reporting period')"
              class="flex gap-1 rounded-md bg-surface-gray-1 p-1"
            >
              <button
                v-for="period in ['month', 'quarter']"
                :key="period"
                :aria-pressed="filters.period === period"
                class="rounded px-3 py-1 text-sm"
                :class="
                  filters.period === period
                    ? 'bg-surface-base shadow-sm text-ink-gray-9'
                    : 'text-ink-gray-5'
                "
                @click="updateFilters({ period })"
              >
                {{ period === 'month' ? __('Month') : __('Quarter') }}
              </button>
            </div>
          </div>
          <div class="grid gap-1">
            <label for="performance-period" class="text-xs text-ink-gray-5">{{
              __('Selected period')
            }}</label>
            <div class="flex items-center gap-1">
              <CRMButton aria-label="Previous period" @click="navigate(-1)"
                >‹</CRMButton
              ><input
                id="performance-period"
                type="month"
                :value="filters.anchor.slice(0, 7)"
                :aria-label="__('Selected period')"
                @change="selectMonth"
              /><CRMButton aria-label="Next period" @click="navigate(1)"
                >›</CRMButton
              ><span
                v-if="filters.period === 'quarter'"
                class="ml-1 text-sm text-ink-gray-6"
                >{{ label }}</span
              >
            </div>
          </div>
        </div>
        <p
          v-if="filters.salesperson === 'team'"
          class="mb-4 text-xs text-ink-gray-5"
        >
          {{ __('Team includes:') }}
          {{ teamLabel || __('No configured salespeople') }}
        </p>
        <div
          v-if="summaryLoading"
          role="status"
          class="rounded-lg border border-outline-gray-1 p-8 text-center text-sm text-ink-gray-5"
        >
          {{ __('Loading target progress…') }}
        </div>
        <div
          v-else-if="summaryError"
          role="alert"
          class="space-y-3 rounded-lg border border-outline-gray-1 p-6 text-sm"
        >
          <p>{{ summaryError }}</p>
          <CRMButton @click="loadSummary()">{{
            __('Retry summary')
          }}</CRMButton>
        </div>
        <template v-else-if="summary">
          <div
            v-if="summary.warnings?.length"
            role="status"
            class="mb-4 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-7"
          >
            <p v-for="warning in summary.warnings" :key="warning">
              {{ warning }}
            </p>
          </div>
          <section
            aria-label="Target progress"
            class="overflow-hidden rounded-lg border border-outline-gray-1"
          >
            <div class="grid grid-cols-2 gap-y-5 py-5 md:grid-cols-4">
              <div class="border-r border-outline-gray-1 px-4 sm:px-6">
                <p class="mb-2 text-xs text-ink-gray-5">{{ __('Target') }}</p>
                <p class="text-3xl font-semibold tabular-nums tracking-tight">
                  {{ money(summary.target) }}
                </p>
                <p class="mt-1 text-xs text-ink-gray-5">
                  {{
                    filters.period === 'quarter'
                      ? __('Sum of 3 monthly targets · USD')
                      : __('Monthly new MRR · USD')
                  }}
                </p>
              </div>
              <div class="px-4 sm:px-6 md:border-r md:border-outline-gray-1">
                <p class="mb-2 text-xs text-ink-gray-5">{{ __('Won MRR') }}</p>
                <p
                  data-testid="actual"
                  class="text-3xl font-semibold tabular-nums tracking-tight"
                >
                  {{ money(summary.actual) }}
                </p>
                <p class="mt-1 text-xs text-ink-gray-5">
                  {{ __('Actual MRR of deals won in period') }}
                </p>
              </div>
              <div class="border-r border-outline-gray-1 px-4 sm:px-6">
                <p class="mb-2 text-xs text-ink-gray-5">
                  {{ __('Attainment') }}
                </p>
                <p class="text-3xl font-semibold tabular-nums tracking-tight">
                  {{
                    summary.progress == null
                      ? '—'
                      : `${Math.round(summary.progress)}%`
                  }}
                </p>
                <p class="mt-1 text-xs text-ink-gray-5">
                  {{ __('Won MRR ÷ target') }}
                </p>
              </div>
              <div class="px-4 sm:px-6">
                <p class="mb-2 text-xs text-ink-gray-5">
                  {{ __('Remaining') }}
                </p>
                <p class="text-3xl font-semibold tabular-nums tracking-tight">
                  {{ money(summary.remaining) }}
                </p>
                <p class="mt-1 text-xs text-ink-gray-5">
                  {{ __('New MRR still needed') }}
                </p>
              </div>
            </div>
            <div class="px-4 pb-5 sm:px-6">
              <div class="mb-2 flex flex-wrap justify-between gap-2 text-xs">
                <span
                  >{{ money(summary.actual) }} {{ __('of') }}
                  {{ money(summary.target) }}</span
                ><span class="text-ink-gray-5">{{ label }}</span>
              </div>
              <div
                role="progressbar"
                :aria-label="__('Target attainment')"
                :aria-valuenow="summary.progress == null ? undefined : progress"
                :aria-valuetext="
                  summary.progress == null
                    ? __('Target not available')
                    : `${Math.round(summary.progress)}%`
                "
                :aria-valuemin="0"
                :aria-valuemax="100"
                class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
              >
                <div
                  class="h-full rounded-full bg-surface-green-7"
                  :style="{ width: progress + '%' }"
                />
              </div>
            </div>
            <div
              class="flex flex-wrap items-center gap-x-7 gap-y-2 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-3 text-xs sm:px-6"
            >
              <span class="text-ink-gray-5"
                >{{ __('Weighted pipeline') }}
                <strong class="ml-2 font-semibold text-ink-gray-9">{{
                  money(summary.weighted_pipeline)
                }}</strong></span
              ><span class="text-ink-gray-5"
                >{{ __('Coverage of remaining target') }}
                <strong class="ml-2 font-semibold text-ink-gray-9">{{
                  coverage
                }}</strong></span
              ><span class="text-ink-gray-5">{{
                __('All open deals · expected MRR × probability')
              }}</span>
            </div>
            <div
              v-if="filters.period === 'quarter'"
              class="flex flex-wrap gap-5 border-t border-outline-gray-1 px-4 py-3 text-xs sm:px-6"
            >
              <span
                v-for="target in summary.targets"
                :key="target.month + (target.salesperson || '')"
                ><span class="text-ink-gray-5"
                  >{{ periodLabel(target.month) }}
                  <template v-if="target.salesperson"
                    >· {{ target.salesperson }}</template
                  ></span
                >
                <strong class="font-medium">{{ money(target.amount) }}</strong>
                <span
                  v-if="target.source === 'recurring'"
                  class="text-ink-gray-5"
                  >({{ __('recurring') }})</span
                ></span
              >
            </div>
          </section>
          <section aria-labelledby="performance-deals-title" class="mt-6">
            <div class="mb-3 flex items-center justify-between gap-3">
              <h2 id="performance-deals-title" class="text-sm font-semibold">
                {{ __('Deals behind the numbers') }}
                <span class="ml-2 text-xs font-normal text-ink-gray-5"
                  >{{ summary.total }} {{ __('deals') }}</span
                >
              </h2>
            </div>
            <div
              class="overflow-x-auto rounded-lg border border-outline-gray-1"
            >
              <table class="w-full whitespace-nowrap text-left text-sm">
                <thead
                  class="bg-surface-gray-1 text-xs font-normal text-ink-gray-5"
                >
                  <tr>
                    <th>{{ __('Organization / deal') }}</th>
                    <th>{{ __('Stage') }}</th>
                    <th class="text-right">{{ __('Expected MRR (USD)') }}</th>
                    <th class="text-right">{{ __('Probability') }}</th>
                    <th class="text-right">{{ __('Contribution (USD)') }}</th>
                    <th>{{ __('Won on') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!summary.deals.length">
                    <td colspan="6" class="text-center text-ink-gray-5">
                      {{ __('No contributing deals for this selection.') }}
                    </td>
                  </tr>
                  <tr v-for="deal in summary.deals" :key="deal.name">
                    <td>
                      <RouterLink
                        :to="{ name: 'Deal', params: { dealId: deal.name } }"
                        class="text-ink-blue-6 hover:underline"
                        >{{ deal.title || deal.name }}</RouterLink
                      >
                    </td>
                    <td>
                      <span
                        class="rounded bg-surface-gray-1 px-2 py-1 text-xs"
                        >{{
                          deal.status ||
                          (deal.kind === 'won' ? __('Won') : __('Open'))
                        }}</span
                      >
                    </td>
                    <td class="text-right tabular-nums">
                      {{ money(deal.expected_mrr) }}
                    </td>
                    <td class="text-right tabular-nums">
                      {{
                        deal.probability == null ? '—' : `${deal.probability}%`
                      }}
                    </td>
                    <td class="text-right tabular-nums">
                      {{
                        money(deal.kind === 'won' ? deal.amount : deal.weighted)
                      }}
                      <span class="text-xs text-ink-gray-5">{{
                        deal.kind === 'won' ? __('actual') : __('weighted')
                      }}</span>
                    </td>
                    <td class="text-xs text-ink-gray-5">
                      {{ deal.won_at || '—' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-if="summary.total > summary.page_size"
              class="mt-3 flex items-center justify-end gap-3 text-xs text-ink-gray-5"
            >
              <CRMButton
                :disabled="dealPage <= 1"
                @click="loadSummary(dealPage - 1)"
                >{{ __('Previous deals') }}</CRMButton
              ><span
                >{{ __('Page') }} {{ dealPage }} {{ __('of') }}
                {{ Math.ceil(summary.total / summary.page_size) }}</span
              ><CRMButton
                :disabled="dealPage * summary.page_size >= summary.total"
                @click="loadSummary(dealPage + 1)"
                >{{ __('Next deals') }}</CRMButton
              >
            </div>
            <p class="mt-3 text-xs text-ink-gray-5">
              {{
                __(
                  'Won contribution uses actual MRR and the transition into Won. Open contribution is probability-weighted expected MRR.',
                )
              }}
            </p>
          </section>
        </template>
        <section aria-labelledby="performance-activity-title" class="mt-7">
          <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 id="performance-activity-title" class="text-sm font-semibold">
              {{ __('Daily activity') }}
              <span class="ml-2 text-xs font-normal text-ink-gray-5">{{
                __('Last 7 days')
              }}</span>
            </h2>
            <div class="flex flex-wrap gap-2">
              <select
                :value="filters.mode"
                aria-label="Activity scope"
                @change="updateFilters({ mode: $event.target.value })"
              >
                <option value="performed_by">
                  {{ __('Performed by salesperson') }}
                </option>
                <option value="owned_records">
                  {{ __('On owned leads & deals') }}
                </option>
              </select>
              <select
                :value="filters.kind"
                aria-label="Activity type"
                @change="updateFilters({ kind: $event.target.value })"
              >
                <option
                  v-for="option in activityTypes"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ __(option.label) }}
                </option>
              </select>
            </div>
          </div>
          <div
            class="mb-3 flex flex-wrap justify-between gap-2 text-xs text-ink-gray-5"
          >
            <span
              >{{
                filters.mode === 'performed_by'
                  ? __('Actions performed by')
                  : __('Changes on records owned by')
              }}
              {{ salespersonLabel }}</span
            ><span
              >{{ activity?.window?.start || ''
              }}<template v-if="activity?.window?.start">
                – {{ activity.window.end }} · </template
              >{{ context.timezone }} ·
              {{ __('independent of target period') }}</span
            >
          </div>
          <div
            v-if="activityLoading"
            role="status"
            class="rounded-lg border border-outline-gray-1 p-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('Loading daily activity…') }}
          </div>
          <div
            v-else-if="activityError"
            role="alert"
            class="space-y-3 rounded-lg border border-outline-gray-1 p-6 text-sm"
          >
            <p>{{ activityError }}</p>
            <CRMButton @click="loadActivity()">{{
              __('Retry activity')
            }}</CRMButton>
          </div>
          <template v-else-if="activity"
            ><div
              v-if="activity.warnings?.length"
              role="status"
              class="mb-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-7"
            >
              <p v-for="warning in activity.warnings" :key="warning">
                {{ warning }}
              </p>
            </div>
            <ActivityList :days="activity.days" :timezone="context.timezone" />
            <div
              v-if="activity.total > activity.page_size"
              class="mt-3 flex items-center justify-end gap-3 text-xs text-ink-gray-5"
            >
              <CRMButton
                :disabled="activityPage <= 1"
                @click="loadActivity(activityPage - 1)"
                >{{ __('Previous activity') }}</CRMButton
              ><span
                >{{ __('Page') }} {{ activityPage }} {{ __('of') }}
                {{ Math.ceil(activity.total / activity.page_size) }}</span
              ><CRMButton
                :disabled="activityPage * activity.page_size >= activity.total"
                @click="loadActivity(activityPage + 1)"
                >{{ __('Next activity') }}</CRMButton
              >
            </div></template
          >
          <p class="mt-3 text-xs text-ink-gray-5">
            {{
              __(
                'Expand a row for source, actor, time, and details. Routine system updates are omitted.',
              )
            }}
          </p>
        </section>
      </template>
    </main>
    <TargetDialog
      v-if="showTarget && context?.manager && summary"
      :key="filters.salesperson + filters.anchor"
      :salesperson="filters.salesperson"
      :salesperson-label="salespersonLabel"
      :today="context.today"
      :months="periodMonths(filters.anchor, filters.period)"
      :targets="summary.targets"
      @close="showTarget = false"
      @saved="targetSaved"
    />
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Button as CRMButton } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import ActivityList from '@/components/Performance/ActivityList.vue'
import TargetDialog from '@/components/Performance/TargetDialog.vue'
import { usePerformance } from '@/composables/usePerformance'
import {
  money,
  periodLabel,
  periodMonths,
  shiftPeriod,
} from '@/utils/performance'

const {
  context,
  contextError,
  contextLoading,
  filters,
  summary,
  activity,
  summaryError,
  activityError,
  summaryLoading,
  activityLoading,
  loadContext,
  loadSummary,
  loadActivity,
  updateFilters,
  dealPage,
  activityPage,
} = usePerformance()
const showTarget = ref(false)
const activityTypes = [
  { value: 'all', label: 'All activity' },
  { value: 'call', label: 'Calls' },
  { value: 'change', label: 'Changes' },
  { value: 'note', label: 'Notes' },
  { value: 'task', label: 'Tasks' },
  { value: 'communication', label: 'Emails' },
  { value: 'comment', label: 'Comments' },
]
const teamLabel = computed(
  () =>
    context.value?.team_users
      ?.map(
        (name) =>
          context.value.users.find((user) => user.name === name)?.full_name ||
          name,
      )
      .join(', ') || '',
)
const salespersonLabel = computed(() =>
  filters.value?.salesperson === 'team'
    ? __('the whole team')
    : context.value?.users.find(
        (user) => user.name === filters.value?.salesperson,
      )?.full_name ||
      filters.value?.salesperson ||
      '',
)
const label = computed(() =>
  filters.value ? periodLabel(filters.value.anchor, filters.value.period) : '',
)
const progress = computed(() =>
  Math.max(0, Math.min(100, summary.value?.progress || 0)),
)
const coverage = computed(() =>
  summary.value?.coverage != null
    ? `${Number(summary.value.coverage).toFixed(1)}×`
    : summary.value?.target > 0 && summary.value.remaining === 0
      ? __('Target met')
      : '—',
)
watch(filters, () => {
  showTarget.value = false
})
function navigate(direction) {
  updateFilters({
    anchor: shiftPeriod(filters.value.anchor, filters.value.period, direction),
  })
}
function selectMonth(event) {
  if (/^\d{4}-(0[1-9]|1[0-2])$/.test(event.target.value))
    updateFilters({ anchor: event.target.value + '-01' })
}
function targetSaved() {
  showTarget.value = false
  loadSummary()
}
</script>
<style scoped>
.performance select,
.performance input {
  @apply min-h-8 rounded-md border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-sm text-ink-gray-9;
}
.performance th,
.performance td {
  @apply border-b border-outline-gray-1 px-4 py-3;
}
.performance th {
  @apply font-normal;
}
.performance tbody tr:last-child td {
  @apply border-b-0;
}
.performance button:focus-visible,
.performance select:focus-visible,
.performance input:focus-visible {
  outline: var(--focus-outline-default);
  outline-offset: 2px;
}
@media (max-width: 400px) {
  .performance select,
  .performance input,
  .performance button {
    min-height: 44px;
  }
}
</style>
