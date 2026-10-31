<template>
  <section class="flex flex-col gap-3 border-t border-outline-gray-2 pt-3">
    <h3 class="font-semibold text-ink-gray-9">
      {{ __('Follow-up sequences') }}
    </h3>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Save a reusable sequence, then schedule its steps for this customer. Any matching reply cancels the remaining emails.',
        )
      }}
    </p>
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
      >{{ __('Sequence') }}
      <select
        v-model="selected"
        :disabled="busy || disabled || editing || uploads.size > 0"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
      >
        <option value="">{{ __('Choose a saved sequence') }}</option>
        <option
          v-for="sequence in sequences"
          :key="sequence.name"
          :value="sequence.name"
        >
          {{ sequence.title }}
        </option>
      </select>
    </label>
    <div class="flex flex-wrap gap-2">
      <Button
        :label="__('New sequence')"
        :disabled="busy || disabled || uploads.size > 0"
        @click="newSequence"
      />
      <Button
        v-if="chosen"
        :label="__('Edit sequence')"
        :disabled="busy || disabled || editing || uploads.size > 0"
        @click="editSequence"
      />
    </div>
    <form
      v-if="editing"
      class="flex flex-col gap-3 rounded border border-outline-gray-2 p-3"
      @submit.prevent="save"
    >
      <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
        >{{ __('Sequence name') }}
        <input
          v-model="template.title"
          required
          :disabled="busy || disabled || uploads.size > 0"
          class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        />
      </label>
      <div
        v-for="(step, index) in template.steps"
        :key="index"
        class="flex flex-col gap-2 border-t border-outline-gray-2 pt-3"
      >
        <div class="flex flex-wrap items-end gap-2">
          <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
            >{{ __('Step {0}: days after start', [index + 1]) }}
            <input
              v-model.number="step.day_offset"
              type="number"
              min="0"
              max="365"
              step="1"
              required
              :disabled="busy || disabled || uploads.size > 0"
              class="w-28 rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
            />
          </label>
          <Button
            :label="__('Remove step')"
            :disabled="
              busy ||
              disabled ||
              uploads.size > 0 ||
              template.steps.length === 1
            "
            @click="template.steps.splice(index, 1)"
          />
        </div>
        <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
          >{{ __('Subject') }}
          <input
            v-model="step.subject"
            required
            :disabled="busy || disabled || uploads.size > 0"
            class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
          />
        </label>
        <RichTextField
          :content="step.content"
          :editable="!busy && !disabled && uploads.size === 0"
          :fixed-menu="true"
          :bubble-menu="false"
          editor-class="prose-sm min-h-24 rounded border border-outline-gray-2 p-2"
          @change="step.content = $event"
          @uploading="setUpload(index, $event)"
        />
      </div>
      <div class="flex flex-wrap gap-2">
        <Button
          :label="__('Add step')"
          :disabled="
            busy || disabled || uploads.size > 0 || template.steps.length >= 20
          "
          @click="addStep"
        />
        <Button
          type="submit"
          variant="solid"
          :label="__('Save sequence')"
          :disabled="busy || disabled || uploads.size > 0"
        />
        <Button
          :label="__('Discard sequence changes')"
          :disabled="busy || disabled || uploads.size > 0"
          @click="discard"
        />
      </div>
      <p class="text-sm text-ink-gray-6">
        {{
          __(
            'Saving a template does not change emails already scheduled from it.',
          )
        }}
      </p>
    </form>
    <form
      v-if="chosen && !editing"
      class="flex flex-col gap-3"
      @submit.prevent="enroll"
    >
      <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
        >{{ __('From') }}
        <select
          v-model="sender"
          required
          :disabled="busy || disabled || uploads.size > 0"
          class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        >
          <option value="" disabled>
            {{ __('Choose your connected mailbox') }}
          </option>
          <option v-for="item in senders" :key="item.email" :value="item.email">
            {{ item.label || item.email }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
        >{{ __('To') }}
        <input
          v-model="recipients"
          required
          :disabled="busy || disabled || uploads.size > 0"
          class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        />
      </label>
      <ScheduleFields
        v-model:wall="start"
        v-model:timezone="timezone"
        :disabled="busy || disabled || uploads.size > 0"
      />
      <div v-if="preview.length" class="rounded bg-surface-gray-2 p-3">
        <p class="mb-2 text-sm font-medium text-ink-gray-8">
          {{ __('Scheduled steps') }}
        </p>
        <ol
          class="flex list-decimal flex-col gap-2 pl-5 text-sm text-ink-gray-7"
        >
          <li v-for="(step, index) in preview" :key="index">
            {{ step.wall.replace('T', ' ') }} {{ timezone }} ·
            {{ step.subject }}
          </li>
        </ol>
      </div>
      <p v-if="previewError" role="alert" class="text-sm text-ink-red-3">
        {{ previewError }}
      </p>
      <Button
        type="submit"
        variant="solid"
        :label="__('Schedule sequence for this customer')"
        :disabled="
          busy || disabled || !sender || !preview.length || !!previewError
        "
      />
    </form>
    <p v-if="error" role="alert" class="text-sm text-ink-red-3">{{ error }}</p>
  </section>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, call } from 'frappe-ui'
import RichTextField from '@/components/RichTextField.vue'
import ScheduleFields from '@/components/EmailWorkspace/ScheduleFields.vue'
import { scheduleInstant, sequencePreview } from '@/utils/emailSchedule'

const props = defineProps({
  disabled: Boolean,
  sequences: { type: Array, default: () => [] },
  senders: { type: Array, default: () => [] },
  referenceDoctype: { type: String, required: true },
  referenceName: { type: String, required: true },
  defaultRecipient: { type: String, default: '' },
  defaultTimezone: { type: String, default: 'UTC' },
})
const emit = defineEmits(['changed', 'dirty', 'busy'])
const uploads = reactive(new Set())
function setUpload(index, value) {
  if (value) uploads.add(index)
  else uploads.delete(index)
}
const selected = ref(''),
  editing = ref(false),
  busy = ref(false),
  error = ref('')
const template = ref({ title: '', steps: [] })
const sender = ref(props.senders[0]?.email || ''),
  recipients = ref(props.defaultRecipient)
const start = ref(''),
  timezone = ref(props.defaultTimezone)
watch(
  () => props.defaultTimezone,
  (value, previous) => {
    if (!start.value && timezone.value === previous) timezone.value = value
  },
)
watch(
  () => props.senders,
  (value) => {
    if (!sender.value) sender.value = value[0]?.email || ''
  },
)
const chosen = computed(() =>
  props.sequences.find((item) => item.name === selected.value),
)
const previewError = ref('')
const preview = computed(() => {
  try {
    if (!chosen.value || !start.value) return []
    return sequencePreview(chosen.value.steps, start.value, timezone.value)
  } catch {
    return []
  }
})
watch([start, timezone, chosen], () => {
  previewError.value = ''
  if (!chosen.value || !start.value) return
  try {
    sequencePreview(chosen.value.steps, start.value, timezone.value)
  } catch (e) {
    previewError.value = e.message
  }
})
watch(editing, (value) => emit('dirty', value))
watch(
  () => busy.value || uploads.size > 0,
  (value) => emit('busy', value),
  { flush: 'sync' },
)
function discard() {
  if (!window.confirm(__('Discard these sequence changes?'))) return
  editing.value = false
}
function newSequence() {
  if (editing.value && !window.confirm(__('Discard these sequence changes?')))
    return
  template.value = {
    title: '',
    steps: [{ day_offset: 0, subject: '', content: '' }],
  }
  editing.value = true
  error.value = ''
}
function editSequence() {
  if (editing.value || busy.value || props.disabled || uploads.size > 0) return
  template.value = JSON.parse(JSON.stringify(chosen.value))
  editing.value = true
  error.value = ''
}
function addStep() {
  const last = Number(template.value.steps.at(-1)?.day_offset || 0)
  template.value.steps.push({ day_offset: last + 3, subject: '', content: '' })
}
async function save() {
  if (busy.value || props.disabled || uploads.size > 0) return
  error.value = ''
  try {
    sequencePreview(template.value.steps, '2030-01-15T09:00', 'UTC')
    if (
      !template.value.title.trim() ||
      template.value.steps.some(
        (step) =>
          !step.subject.trim() || !step.content.replace(/<[^>]*>/g, '').trim(),
      )
    )
      throw new Error(
        __(
          'Each sequence needs a name, and each step needs a subject and message.',
        ),
      )
    busy.value = true
    const result = await call('crm.api.scheduled_email.save_sequence', {
      data: {
        name: template.value.name,
        modified: template.value.modified,
        title: template.value.title,
        steps: template.value.steps.map(({ day_offset, subject, content }) => ({
          day_offset: Number(day_offset),
          subject,
          content,
        })),
      },
    })
    selected.value = result.name
    editing.value = false
    emit('changed')
  } catch (e) {
    error.value =
      e.messages?.join(' ') ||
      e.message ||
      __('Could not save this sequence. Your changes are still here.')
  } finally {
    busy.value = false
  }
}
async function enroll() {
  if (busy.value || props.disabled || uploads.size > 0 || !chosen.value) return
  error.value = ''
  try {
    const steps = sequencePreview(
      chosen.value.steps,
      start.value,
      timezone.value,
    )
    const base = scheduleInstant(start.value, timezone.value)
    if (new Date(base).getTime() <= Date.now())
      throw new Error(__('Choose a future start time.'))
    if (
      !window.confirm(
        __('Schedule all {0} emails for this customer?', [steps.length]),
      )
    )
      return
    busy.value = true
    await call('crm.api.scheduled_email.enroll_sequence', {
      reference_doctype: props.referenceDoctype,
      reference_name: props.referenceName,
      sequence_name: chosen.value.name,
      start_at: base,
      timezone: timezone.value,
      sender: sender.value,
      recipients: recipients.value,
    })
    start.value = ''
    emit('changed')
  } catch (e) {
    error.value =
      e.messages?.join(' ') ||
      e.message ||
      __('Could not schedule this sequence.')
  } finally {
    busy.value = false
  }
}
</script>
