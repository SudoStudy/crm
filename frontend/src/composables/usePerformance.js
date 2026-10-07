import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { call } from 'frappe-ui'
import { normalizeFilters } from '@/utils/performance'

export function usePerformance() {
  const route = useRoute()
  const router = useRouter()
  const context = ref(null)
  const contextError = ref('')
  const contextLoading = ref(false)
  const filters = computed(() =>
    context.value ? normalizeFilters(route.query, context.value) : null,
  )
  const summary = ref(null)
  const activity = ref(null)
  const summaryError = ref('')
  const activityError = ref('')
  const summaryLoading = ref(false)
  const activityLoading = ref(false)
  const dealPage = ref(1)
  const activityPage = ref(1)
  let summaryRequest = 0
  let activityRequest = 0
  let contextRequest = 0

  async function loadContext() {
    const request = ++contextRequest
    contextLoading.value = true
    contextError.value = ''
    try {
      const data = await call('crm.api.performance.get_context')
      if (request === contextRequest) context.value = data
    } catch (error) {
      if (request === contextRequest)
        contextError.value =
          error.message || 'Unable to load Performance access.'
    } finally {
      if (request === contextRequest) contextLoading.value = false
    }
  }

  async function loadSummary(page = dealPage.value) {
    if (!filters.value) return
    const request = ++summaryRequest
    summaryLoading.value = true
    summaryError.value = ''
    summary.value = null
    dealPage.value = page
    const { salesperson, period, anchor } = filters.value
    try {
      const data = await call('crm.api.performance.get_summary', {
        salesperson,
        period,
        anchor,
        page,
        page_size: 20,
      })
      if (request === summaryRequest) summary.value = data
    } catch (error) {
      if (request === summaryRequest)
        summaryError.value = error.message || 'Unable to load target progress.'
    } finally {
      if (request === summaryRequest) summaryLoading.value = false
    }
  }

  async function loadActivity(page = activityPage.value) {
    if (!filters.value) return
    const request = ++activityRequest
    activityLoading.value = true
    activityError.value = ''
    activity.value = null
    activityPage.value = page
    const { salesperson, mode, kind } = filters.value
    try {
      const data = await call('crm.api.performance.get_activity', {
        salesperson,
        mode,
        kind,
        page,
        page_size: 50,
      })
      if (request === activityRequest) activity.value = data
    } catch (error) {
      if (request === activityRequest)
        activityError.value = error.message || 'Unable to load daily activity.'
    } finally {
      if (request === activityRequest) activityLoading.value = false
    }
  }

  function updateFilters(changes) {
    return router.replace({
      query: {
        ...route.query,
        ...normalizeFilters({ ...filters.value, ...changes }, context.value),
      },
    })
  }

  watch(
    () =>
      filters.value &&
      [
        filters.value.salesperson,
        filters.value.period,
        filters.value.anchor,
      ].join('|'),
    () => loadSummary(1),
  )
  watch(
    () =>
      filters.value &&
      [filters.value.salesperson, filters.value.mode, filters.value.kind].join(
        '|',
      ),
    () => loadActivity(1),
  )
  onBeforeUnmount(() => {
    summaryRequest++
    activityRequest++
    contextRequest++
  })
  loadContext()

  return {
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
  }
}
