<template>
  <form
    class="flex flex-col gap-3 rounded border border-outline-gray-2 p-3"
    @submit.prevent="emit('save')"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="text-base font-semibold text-ink-gray-9">{{
        draft.name ? __('Edit email') : __('New draft')
      }}</span>
      <Button
        :label="__('Close editor')"
        :disabled="busy"
        @click="emit('close')"
      />
    </div>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Save to keep this complete draft across devices. Opening a scheduled email for editing pauses it until you schedule it again.',
        )
      }}
    </p>
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
      >{{ __('From') }}
      <select
        v-model="draft.sender"
        :disabled="busy"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
      >
        <option value="" disabled>
          {{ __('Choose your connected mailbox') }}
        </option>
        <option
          v-for="sender in senders"
          :key="sender.email"
          :value="sender.email"
        >
          {{ sender.label || sender.email }}
        </option>
      </select>
    </label>
    <p
      v-if="
        draft.sender &&
        !senders.some(
          (item) => item.email.toLowerCase() === draft.sender.toLowerCase(),
        )
      "
      class="text-sm text-ink-red-3"
    >
      {{
        __(
          'This sending mailbox is no longer available. Choose a connected mailbox before sending.',
        )
      }}
    </p>
    <label
      v-for="field in recipientFields"
      :key="field.key"
      class="flex flex-col gap-1 text-sm text-ink-gray-7"
    >
      {{ __(field.label) }}
      <input
        v-model="draft[field.key]"
        :disabled="busy"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
        :placeholder="__('Comma-separated email addresses')"
      />
    </label>
    <label class="flex flex-col gap-1 text-sm text-ink-gray-7"
      >{{ __('Subject') }}
      <input
        v-model="draft.subject"
        :disabled="busy"
        class="rounded border border-outline-gray-2 bg-surface-white p-2 text-ink-gray-9"
      />
    </label>
    <label class="text-sm text-ink-gray-7">{{ __('Message') }}</label>
    <RichTextField
      :content="draft.content"
      :editable="!busy"
      :fixed-menu="true"
      :bubble-menu="false"
      editor-class="prose-sm min-h-36 rounded border border-outline-gray-2 p-2"
      @change="draft.content = $event"
      @uploading="inlineUploading = $event"
    />
    <div class="flex flex-wrap items-center gap-2">
      <FileUploader
        :upload-args="{
          doctype: referenceDoctype,
          docname: referenceName,
          private: true,
        }"
        :validate-file="beginAttachmentUpload"
        @success="addAttachment"
        @failure="attachmentFailed"
      >
        <template #default="{ openFileSelector }"
          ><Button
            :label="__('Attach a file')"
            :disabled="busy"
            @click="openFileSelector()"
        /></template>
      </FileUploader>
      <span
        v-for="file in draft.attachments"
        :key="file"
        class="flex items-center gap-1 rounded bg-surface-gray-2 px-2 py-1 text-sm text-ink-gray-8"
      >
        {{ file }}
        <Button
          :label="__('Remove')"
          :disabled="busy"
          @click="
            draft.attachments = draft.attachments.filter(
              (name) => name !== file,
            )
          "
        />
      </span>
    </div>
    <p v-if="uploadError" role="alert" class="text-sm text-ink-red-3">
      {{ uploadError }}
    </p>
    <label class="flex items-center gap-2 text-sm text-ink-gray-7"
      ><input
        v-model="draft.stop_on_reply"
        type="checkbox"
        :disabled="busy"
      />{{ __('Cancel if this customer replies before sending') }}</label
    >
    <ScheduleFields
      v-model:wall="wall"
      v-model:timezone="timezone"
      :disabled="busy"
    />
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Times use the timezone above. Replies must reach CRM before sending to stop an email. Messages already handed to the provider cannot be recalled.',
        )
      }}
    </p>
    <div class="flex flex-wrap gap-2">
      <Button
        type="submit"
        :label="__('Save draft')"
        :disabled="busy"
        :loading="busy"
        variant="solid"
      />
      <Button
        :label="__('Send now')"
        :disabled="busy || !canSend"
        @click="emit('send-now')"
      />
      <Button
        :label="__('Schedule email')"
        :disabled="busy || !canSend || !wall"
        @click="emit('schedule')"
      />
    </div>
  </form>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button, FileUploader } from 'frappe-ui'
import RichTextField from '@/components/RichTextField.vue'
import ScheduleFields from '@/components/EmailWorkspace/ScheduleFields.vue'

const props = defineProps({
  senders: { type: Array, default: () => [] },
  busy: Boolean,
  referenceDoctype: { type: String, required: true },
  referenceName: { type: String, required: true },
})
const draft = defineModel('draft', { type: Object, required: true })
const wall = defineModel('wall', { type: String, default: '' })
const timezone = defineModel('timezone', { type: String, default: 'UTC' })
const emit = defineEmits(['save', 'schedule', 'send-now', 'close', 'uploading'])
const canSend = computed(
  () =>
    props.senders.some(
      (item) => item.email.toLowerCase() === draft.value.sender.toLowerCase(),
    ) && !!draft.value.recipients.trim(),
)
const recipientFields = [
  { key: 'recipients', label: 'To' },
  { key: 'cc', label: 'CC' },
  { key: 'bcc', label: 'BCC' },
]
const attachmentUploading = ref(false),
  inlineUploading = ref(false),
  uploadError = ref('')
let active = true,
  attachmentTarget
watch(
  () => attachmentUploading.value || inlineUploading.value,
  (value) => emit('uploading', value),
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  active = false
})
function beginAttachmentUpload() {
  if (!active || props.busy)
    return new Error(__('Wait for the current action to finish.'))
  attachmentTarget = draft.value
  attachmentUploading.value = true
  uploadError.value = ''
  return null
}
function attachmentFailed() {
  attachmentUploading.value = false
  if (active)
    uploadError.value = __(
      'The attachment could not be uploaded. Please try again before sending.',
    )
}
function addAttachment(file) {
  if (
    active &&
    attachmentTarget === draft.value &&
    typeof file?.name === 'string' &&
    !attachmentTarget.attachments.includes(file.name)
  )
    attachmentTarget.attachments.push(file.name)
  attachmentUploading.value = false
}
</script>
