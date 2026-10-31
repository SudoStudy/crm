<template>
  <section class="border-t border-outline-gray-2 px-4 py-3">
    <Button
      :label="
        opened
          ? __('Hide drafts & scheduled emails')
          : __('Drafts & scheduled emails')
      "
      icon-left="mail"
      :disabled="allBusy"
      @click="toggle"
    />
    <div v-if="opened" class="mt-3 flex flex-col gap-3">
      <p class="text-sm text-ink-gray-6">
        {{
          __(
            'Your saved drafts, scheduled emails and follow-up sequences for this customer.',
          )
        }}
      </p>
      <div class="flex flex-wrap gap-2">
        <Button
          :label="__('New saved draft')"
          :disabled="allBusy || loading"
          @click="edit()"
        />
        <Button
          :label="__('Refresh emails')"
          :disabled="allBusy || loading"
          @click="load"
        />
      </div>
      <p v-if="loading" role="status" class="text-sm text-ink-gray-6">
        {{ __('Loading emails…') }}
      </p>
      <p v-if="error" role="alert" class="text-sm text-ink-red-3">
        {{ error }}
      </p>
      <p v-if="notice" role="status" class="text-sm text-ink-gray-7">
        {{ notice }}
      </p>
      <p
        v-if="!loading && !workspace.senders.length"
        class="text-sm text-ink-gray-7"
      >
        {{
          __(
            'Connect your mailbox in Settings → Profile before scheduling email. Your drafts can still be saved.',
          )
        }}
      </p>
      <EmailDraftEditor
        v-if="draft"
        :key="referenceDoctype + referenceName + editorVersion"
        v-model:draft="draft"
        v-model:wall="wall"
        v-model:timezone="timezone"
        :senders="workspace.senders"
        :busy="allBusy"
        :reference-doctype="referenceDoctype"
        :reference-name="referenceName"
        @save="save('draft')"
        @schedule="save('schedule')"
        @send-now="save('now')"
        @close="closeEditor"
        @uploading="uploading = $event"
      />
      <p
        v-if="!loading && !workspace.drafts.length"
        class="text-sm text-ink-gray-6"
      >
        {{ __('No saved emails for this customer yet.') }}
      </p>
      <ul class="flex flex-col gap-2">
        <li
          v-for="item in workspace.drafts"
          :key="item.name"
          class="flex flex-col gap-2 rounded border border-outline-gray-2 p-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span class="break-words font-medium text-ink-gray-9">{{
              item.subject || __('Untitled draft')
            }}</span>
            <Badge :label="__(item.status)" variant="subtle" />
          </div>
          <p class="break-words text-sm text-ink-gray-6">
            {{ item.sender }} → {{ item.recipients }}
          </p>
          <p v-if="item.send_at" class="text-sm text-ink-gray-7">
            {{ formatTime(item) }}
          </p>
          <p v-if="item.enrollment_id" class="text-sm text-ink-gray-6">
            {{ __('Part of a follow-up sequence') }}
          </p>
          <p
            v-if="item.stop_on_reply && item.status === 'Scheduled'"
            class="text-sm text-ink-gray-6"
          >
            {{ __('Will cancel if this customer replies') }}
          </p>
          <p v-if="item.last_error" class="text-sm text-ink-red-3">
            {{ item.last_error }}
          </p>
          <p v-if="item.status === 'Error'" class="text-sm text-ink-gray-7">
            {{
              __(
                'Check the email history and provider before creating another email. A delivery attempt may have succeeded; this email will not retry automatically.',
              )
            }}
          </p>
          <div class="flex flex-wrap gap-2">
            <Button
              v-if="emailStatusActions(item.status).edit"
              :label="__('Edit email')"
              :disabled="allBusy"
              @click="edit(item)"
            />
            <Button
              v-if="emailStatusActions(item.status).cancel"
              :label="__('Cancel email')"
              :disabled="allBusy"
              @click="mutate('cancel_email', item)"
            />
            <Button
              v-if="item.enrollment_id && item.status === 'Scheduled'"
              :label="__('Cancel remaining sequence')"
              :disabled="allBusy"
              @click="cancelEnrollment(item)"
            />
            <Button
              v-if="
                emailStatusActions(item.status).remove && !item.communication
              "
              :label="__('Delete draft')"
              :disabled="allBusy"
              @click="mutate('delete_draft', item)"
            />
          </div>
        </li>
      </ul>
      <p v-if="workspace.history_truncated" class="text-sm text-ink-gray-6">
        {{
          __(
            'Showing the latest 100 completed or canceled emails, plus all pending emails.',
          )
        }}
      </p>
      <EmailSequencePanel
        :key="referenceDoctype + ':' + referenceName"
        :sequences="workspace.sequences"
        :senders="workspace.senders"
        :reference-doctype="referenceDoctype"
        :reference-name="referenceName"
        :default-recipient="defaultRecipient"
        :default-timezone="workspace.timezone"
        :disabled="busy || loading"
        @busy="sequenceBusy = $event"
        @dirty="sequenceDirty = $event"
        @changed="load"
      />
    </div>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { Badge, Button, call } from 'frappe-ui'
import EmailDraftEditor from '@/components/EmailWorkspace/EmailDraftEditor.vue'
import EmailSequencePanel from '@/components/EmailWorkspace/EmailSequencePanel.vue'
import { useUnsavedChangesWarning } from '@/composables/useUnsavedChangesWarning'
import {
  draftFields,
  emailStatusActions,
  scheduleInstant,
  scheduleWallTime,
} from '@/utils/emailSchedule'

const props = defineProps({
  referenceDoctype: { type: String, required: true },
  referenceName: { type: String, required: true },
  defaultRecipient: { type: String, default: '' },
})
const emit = defineEmits(['changed'])
const emptyWorkspace = () => ({
  drafts: [],
  sequences: [],
  senders: [],
  timezone: 'UTC',
})
const workspace = ref(emptyWorkspace()),
  opened = ref(false),
  loading = ref(false),
  busy = ref(false)
const error = ref(''),
  notice = ref(''),
  draft = ref(null),
  baseline = ref(''),
  sequenceDirty = ref(false)
const sequenceBusy = ref(false),
  uploading = ref(false),
  editorVersion = ref(0)
const allBusy = computed(
  () => busy.value || sequenceBusy.value || uploading.value,
)
const wall = ref(''),
  timezone = ref('UTC')
let generation = 0
const editorSnapshot = () =>
  JSON.stringify({
    draft: draft.value,
    wall: wall.value,
    timezone: timezone.value,
  })
const dirty = computed(
  () =>
    sequenceDirty.value ||
    (!!draft.value && editorSnapshot() !== baseline.value),
)
useUnsavedChangesWarning(() => dirty.value)
const mayLeave = () =>
  !allBusy.value &&
  (!dirty.value ||
    window.confirm(__('Leave without saving your email changes?')))
onBeforeRouteLeave(mayLeave)
onBeforeRouteUpdate(mayLeave)
onBeforeUnmount(() => {
  generation++
})
watch(
  () => [props.referenceDoctype, props.referenceName],
  () => {
    generation++
    workspace.value = emptyWorkspace()
    draft.value = null
    error.value = notice.value = ''
    sequenceDirty.value = false
    sequenceBusy.value = false
    uploading.value = false
    busy.value = false
    if (opened.value) load()
  },
)
function toggle() {
  if (opened.value && !mayLeave()) return
  opened.value = !opened.value
  if (opened.value) load()
  else sequenceDirty.value = false
}
async function load() {
  const request = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await call('crm.api.scheduled_email.get_workspace', {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
    })
    if (request === generation)
      workspace.value = { ...emptyWorkspace(), ...result }
  } catch (e) {
    if (request === generation)
      error.value =
        e.messages?.join(' ') || e.message || __('Could not load saved emails.')
  } finally {
    if (request === generation) loading.value = false
  }
}
function closeEditor() {
  if (allBusy.value) return
  if (dirty.value && !window.confirm(__('Discard unsaved draft changes?')))
    return
  draft.value = null
}
function updateRow(saved) {
  const index = workspace.value.drafts.findIndex(
    (item) => item.name === saved.name,
  )
  if (index >= 0) workspace.value.drafts.splice(index, 1, saved)
  else workspace.value.drafts.unshift(saved)
}
function openDraft(item, hint) {
  draft.value = draftFields(item, {
    reference_doctype: props.referenceDoctype,
    reference_name: props.referenceName,
    sender: workspace.value.senders[0]?.email,
    recipients: props.defaultRecipient,
  })
  timezone.value =
    item?.timezone || hint?.timezone || workspace.value.timezone || 'UTC'
  const previousTime = item?.send_at || hint?.send_at
  wall.value = previousTime
    ? scheduleWallTime(previousTime, timezone.value)
    : ''
  baseline.value = editorSnapshot()
  editorVersion.value++
}
async function edit(item) {
  if (allBusy.value) return
  if (
    draft.value &&
    dirty.value &&
    !window.confirm(__('Discard unsaved draft changes?'))
  )
    return
  error.value = notice.value = ''
  if (item?.status !== 'Scheduled') {
    openDraft(item)
    return
  }
  if (
    !window.confirm(
      __(
        'Pause this scheduled email so you can edit it? It will not send until you schedule it again.',
      ),
    )
  )
    return
  const request = generation
  const reference = props.referenceDoctype + ':' + props.referenceName
  busy.value = true
  try {
    const paused = await call('crm.api.scheduled_email.unschedule_draft', {
      name: item.name,
      modified: item.modified,
    })
    if (request !== generation) return
    updateRow(paused)
    openDraft(paused, item)
    notice.value = __(
      'Email paused. Schedule it again when your changes are ready.',
    )
  } catch (e) {
    if (request !== generation) return
    await load()
    if (reference === props.referenceDoctype + ':' + props.referenceName)
      error.value =
        e.messages?.join(' ') ||
        e.message ||
        __(
          'Could not confirm that the email was paused. Check its refreshed status before editing.',
        )
  } finally {
    busy.value = false
  }
}
async function save(mode) {
  if (allBusy.value || !draft.value) return
  const request = generation
  busy.value = true
  error.value = notice.value = ''
  let draftSaved = false
  try {
    let instant
    if (mode === 'schedule') {
      instant = scheduleInstant(wall.value, timezone.value)
      if (new Date(instant).getTime() <= Date.now())
        throw new Error(__('Choose a future send time.'))
    }
    if (
      mode === 'now' &&
      !window.confirm(
        __('Send this email now to {0}?', [draft.value.recipients]),
      )
    )
      return
    let saved = await call('crm.api.scheduled_email.save_draft', {
      data: { ...draft.value },
    })
    if (request !== generation) return
    updateRow(saved)
    draftSaved = true
    draft.value = draftFields(saved, {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
    })
    baseline.value = editorSnapshot()
    if (mode !== 'draft') {
      saved = await call(
        mode === 'now'
          ? 'crm.api.scheduled_email.send_draft_now'
          : 'crm.api.scheduled_email.schedule_draft',
        {
          name: saved.name,
          modified: saved.modified,
          ...(mode === 'schedule'
            ? { send_at: instant, timezone: timezone.value }
            : {}),
        },
      )
      if (request !== generation) return
      draft.value = null
    }
    notice.value =
      mode === 'now'
        ? __('Email queued to send now. Refresh to check its status.')
        : mode === 'schedule'
          ? __('Email scheduled. You can edit or cancel it below.')
          : __(
              'Draft saved. It is available when you sign in on another device.',
            )
    emit('changed')
    await load()
  } catch (e) {
    if (request === generation) {
      const detail =
        e.messages?.join(' ') ||
        e.message ||
        __('Please try again after checking the refreshed status.')
      error.value =
        draftSaved && mode !== 'draft'
          ? __(
              'Your draft was saved, but {0} was not confirmed. Refresh the list before trying again. {1}',
              [mode === 'now' ? __('sending') : __('scheduling'), detail],
            )
          : detail
    }
  } finally {
    busy.value = false
  }
}
async function mutate(method, item) {
  if (busy.value) return
  const prompt =
    method === 'delete_draft'
      ? __('Permanently delete this saved draft?')
      : __(
          'Cancel this email? Other sequence steps can be canceled separately.',
        )
  if (!window.confirm(prompt)) return
  busy.value = true
  error.value = ''
  const request = generation
  try {
    await call(`crm.api.scheduled_email.${method}`, {
      name: item.name,
      modified: item.modified,
    })
    if (request !== generation) return
    if (draft.value?.name === item.name) draft.value = null
    emit('changed')
    await load()
  } catch (e) {
    if (request === generation)
      error.value =
        e.messages?.join(' ') ||
        e.message ||
        __('Could not update this email. Refresh and try again.')
  } finally {
    busy.value = false
  }
}
async function cancelEnrollment(item) {
  if (
    allBusy.value ||
    !window.confirm(
      __(
        'Cancel all remaining emails in this sequence? Emails already sending or sent cannot be recalled.',
      ),
    )
  )
    return
  busy.value = true
  const request = generation
  error.value = ''
  try {
    const result = await call('crm.api.scheduled_email.cancel_enrollment', {
      enrollment_id: item.enrollment_id,
    })
    if (request !== generation) return
    notice.value = result.already_sending
      ? __(
          'Remaining emails canceled. An email already sending cannot be recalled.',
        )
      : __('Remaining sequence emails canceled.')
    if (
      draft.value &&
      workspace.value.drafts.some(
        (row) =>
          row.name === draft.value.name &&
          row.enrollment_id === item.enrollment_id,
      )
    )
      draft.value = null
    emit('changed')
    await load()
  } catch (e) {
    if (request === generation)
      error.value =
        e.messages?.join(' ') ||
        e.message ||
        __('Could not cancel this sequence. Refresh and try again.')
  } finally {
    busy.value = false
  }
}
function formatTime(item) {
  try {
    return `${scheduleWallTime(item.send_at, item.timezone || 'UTC').replace('T', ' ')} ${item.timezone || 'UTC'}`
  } catch {
    return item.send_at
  }
}
</script>
