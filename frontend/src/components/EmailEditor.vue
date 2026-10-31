<template>
  <Editor
    ref="textEditor"
    v-model="content"
    :extensions="extensions"
    :placeholder="placeholder"
    :editable="editable"
    :upload-function="uploadInlineFile"
  >
    <div class="relative w-full">
      <div class="flex flex-col gap-3">
        <div
          v-if="from.length"
          class="mx-4 flex items-center gap-2 border-t pt-2.5 h-10"
        >
          <span class="text-xs text-ink-gray-4">{{ __('FROM') }}:</span>
          <FormControl
            v-model="fromEmail"
            type="select"
            variant="ghost"
            class="w-full"
            :placeholder="__('')"
            :options="from"
          />
        </div>
        <div
          class="mx-4 flex items-center gap-2"
          :class="from.length ? '' : 'border-t pt-2.5'"
        >
          <span class="text-xs text-ink-gray-4 mr-2">{{ __('TO') }}:</span>
          <MultiSelectEmailInput
            v-model="toEmails"
            class="flex-1"
            variant="ghost"
            :validate="validateEmail"
            :error-message="
              (value) => __('{0} is an invalid email address', [value])
            "
          />
          <div class="flex gap-1.5">
            <Button
              :label="__('CC')"
              variant="ghost"
              :class="[
                cc
                  ? '!bg-surface-gray-4 hover:bg-surface-gray-3'
                  : '!text-ink-gray-4',
              ]"
              @click="toggleCC()"
            />
            <Button
              :label="__('BCC')"
              variant="ghost"
              :class="[
                bcc
                  ? '!bg-surface-gray-4 hover:bg-surface-gray-3'
                  : '!text-ink-gray-4',
              ]"
              @click="toggleBCC()"
            />
          </div>
        </div>
        <div v-if="cc" class="mx-4 flex items-center gap-2">
          <span class="text-xs text-ink-gray-4">{{ __('CC') }}:</span>
          <MultiSelectEmailInput
            ref="ccInput"
            v-model="ccEmails"
            class="flex-1"
            variant="ghost"
            :fetchContacts="true"
            :validate="validateEmail"
            :error-message="
              (value) => __('{0} is an invalid email address', [value])
            "
          />
        </div>
        <div v-if="bcc" class="mx-4 flex items-center gap-2">
          <span class="text-xs text-ink-gray-4">{{ __('BCC') }}:</span>
          <MultiSelectEmailInput
            ref="bccInput"
            v-model="bccEmails"
            class="flex-1"
            variant="ghost"
            :fetchContacts="true"
            :validate="validateEmail"
            :error-message="
              (value) => __('{0} is an invalid email address', [value])
            "
          />
        </div>
        <div class="mx-4 flex items-center gap-2 pb-2.5">
          <span class="text-xs text-ink-gray-4">{{ __('SUBJECT') }}:</span>
          <input
            v-model="subject"
            class="flex-1 border-none text-ink-gray-9 text-base bg-surface-base hover:bg-surface-base focus:border-none focus:!shadow-none focus-visible:!ring-0"
          />
        </div>
      </div>
      <EditorContent
        :class="[
          'prose-sm max-w-none [&_p.reply-to-content]:hidden',
          editable && 'mx-4 max-h-[35vh] overflow-y-auto border-t py-3',
        ]"
      />
      <EditorTableMenu />
      <div v-if="editable" class="flex flex-col gap-2">
        <div class="flex flex-wrap gap-2 px-4">
          <AttachmentItem
            v-for="a in attachments"
            :key="a.file_url"
            :label="a.file_name"
          >
            <template #suffix>
              <span
                class="lucide-x h-3.5"
                aria-hidden="true"
                @click.stop="removeAttachment(a)"
              />
            </template>
          </AttachmentItem>
        </div>
        <div class="flex flex-wrap justify-between gap-2 border-t px-4 py-2.5">
          <div class="flex gap-1 items-center overflow-x-auto">
            <Button
              :tooltip="__('Insert Email Template')"
              variant="ghost"
              :icon="EmailTemplateIcon"
              @click="showEmailTemplateSelectorModal = true"
            />
            <FileUploader
              :validate-file="beginAttachmentUpload"
              :upload-args="{
                doctype: doctype,
                docname: modelValue.name,
                private: true,
              }"
              @success="addAttachment"
              @failure="attachmentFailed"
            >
              <template #default="{ openFileSelector }">
                <Button
                  :tooltip="__('Attach a File')"
                  :icon="AttachmentIcon"
                  variant="ghost"
                  :disabled="busy || uploading"
                  @click="openFileSelector()"
                />
              </template>
            </FileUploader>
            <EditorFixedMenu :items="fullToolbar" />
            <IconPicker
              v-slot="{ togglePopover }"
              v-model="emoji"
              @update:modelValue="() => appendEmoji()"
            >
              <Button
                :tooltip="__('Insert Emoji')"
                :icon="SmileIcon"
                variant="ghost"
                @click="togglePopover()"
              />
            </IconPicker>
          </div>
          <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
            <Button v-bind="discardButtonProps || {}" :label="__('Discard')" />
            <slot name="secondary-actions" />
            <Button
              variant="solid"
              v-bind="submitButtonProps || {}"
              :label="`${submitLabel || __('Send')} (${submitShortcutLabel})`"
            />
          </div>
        </div>
      </div>
      <p
        v-if="uploadError"
        role="alert"
        class="px-4 pb-2 text-sm text-ink-red-3"
      >
        {{ uploadError }}
      </p>
    </div>
  </Editor>
  <EmailTemplateSelectorModal
    v-model="showEmailTemplateSelectorModal"
    :doctype="doctype"
    @apply="applyEmailTemplate"
  />
</template>

<script setup>
import IconPicker from '@/components/IconPicker.vue'
import SmileIcon from '@/components/Icons/SmileIcon.vue'
import EmailTemplateIcon from '@/components/Icons/EmailTemplateIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import AttachmentItem from '@/components/AttachmentItem.vue'
import MultiSelectEmailInput from '@/components/Controls/MultiSelectEmailInput.vue'
import EmailTemplateSelectorModal from '@/components/Modals/EmailTemplateSelectorModal.vue'
import {
  buildEditorExtensions,
  fullToolbar,
  uploadFile,
} from '@/components/editor/config'
import { FileUploader, call, FormControl } from 'frappe-ui'
import {
  Editor,
  EditorContent,
  EditorFixedMenu,
  EditorTableMenu,
} from 'frappe-ui/editor'
import { useTelemetry } from 'frappe-ui/frappe'
import { useDocument } from '@/data/document'
import { validateEmail, submitShortcutLabel } from '@/utils'
import Paragraph from '@tiptap/extension-paragraph'
import { ref, computed, nextTick, inject, watch } from 'vue'

const props = defineProps({
  placeholder: { type: String, default: null },
  editable: { type: Boolean, default: true },
  doctype: { type: String, default: 'CRM Lead' },
  subject: { type: String, default: __('Email From Lead') },
  editorProps: { type: Object, default: () => ({}) },
  submitButtonProps: { type: Object, default: () => ({}) },
  discardButtonProps: { type: Object, default: () => ({}) },
  submitLabel: { type: String, default: '' },
  busy: Boolean,
})
const emit = defineEmits(['uploading'])

const CustomParagraph = Paragraph.extend({
  addAttributes() {
    return {
      class: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.class) {
            return {}
          }
          return {
            class: `${attributes.class}`,
          }
        },
      },
    }
  },
})

const modelValue = defineModel({ type: Object })
const attachments = defineModel('attachments', {
  type: Array,
  default: () => [],
})
const content = defineModel('content', { type: String, default: '' })

const { capture } = useTelemetry()
const { user: sessionUser } = inject('session')
const { document: user } = useDocument('User', sessionUser)

const textEditor = ref(null)
const cc = ref(false)
const bcc = ref(false)
const emoji = ref('')

const subject = ref(props.subject)
const fromEmail = ref('')
const toEmails = ref(modelValue.value.email ? [modelValue.value.email] : [])
const ccEmails = ref([])
const bccEmails = ref([])
const ccInput = ref(null)
const bccInput = ref(null)
const attachmentUploading = ref(false)
const inlineUploads = ref(0)
const uploadError = ref('')
const uploading = computed(
  () => attachmentUploading.value || inlineUploads.value > 0,
)
watch(uploading, (value) => emit('uploading', value), { flush: 'sync' })

function beginAttachmentUpload() {
  if (props.busy || uploading.value)
    return new Error(__('Wait for the current action to finish.'))
  attachmentUploading.value = true
  uploadError.value = ''
  return null
}
function addAttachment(file) {
  if (!attachments.value.some((item) => item.name === file.name))
    attachments.value.push(file)
  attachmentUploading.value = false
}
function attachmentFailed() {
  attachmentUploading.value = false
  uploadError.value = __(
    'The attachment could not be uploaded. Please try again.',
  )
}
async function uploadInlineFile(file) {
  if (props.busy) throw new Error(__('Wait for the current action to finish.'))
  inlineUploads.value++
  uploadError.value = ''
  try {
    return await uploadFile(file, props.doctype, modelValue.value.name)
  } catch (error) {
    uploadError.value = __('The image could not be uploaded. Please try again.')
    throw error
  } finally {
    inlineUploads.value--
  }
}

const extensions = buildEditorExtensions({
  starterKit: { paragraph: false },
  extra: [CustomParagraph],
})

const from = computed(() => {
  if (!user.doc || !user.doc.user_emails?.length) return []
  let emails = user.doc.user_emails.map((e) => {
    return {
      label: e.email_account + ' <' + e.email_id + '>',
      value: e.email_id,
    }
  })

  if (emails.length == 1 && emails[0].email_id === sessionUser) return []

  return emails
})

const replyAddresses = ref([])

watch(
  [from, replyAddresses],
  ([fromOptions, addresses]) => {
    let match = addresses.find((a) => fromOptions.some((f) => f.value === a))
    if (match) {
      fromEmail.value = match
      replyAddresses.value = []
    } else if (!fromOptions.find((f) => f.value === fromEmail.value)) {
      fromEmail.value = fromOptions.length ? fromOptions[0].value : ''
    }
  },
  { immediate: true },
)

const editor = computed(() => textEditor.value?.editor)

function removeAttachment(attachment) {
  if (props.busy || uploading.value) return
  attachments.value = attachments.value.filter((a) => a !== attachment)
}

const showEmailTemplateSelectorModal = ref(false)

async function applyEmailTemplate(template) {
  if (props.busy) return
  let doc = modelValue.value

  let data = await call(
    'frappe.email.doctype.email_template.email_template.get_email_template',
    {
      template_name: template.name,
      // fields are the template context, so nesting doc lets {{ doc.field }} work too
      doc: { ...doc, doc },
    },
  )

  if (props.busy) return
  if (data.subject) {
    subject.value = data.subject
  }

  if (data.message) {
    content.value = data.message
  }
  showEmailTemplateSelectorModal.value = false
  capture('email_template_applied', { doctype: props.doctype })
}

function appendEmoji() {
  if (props.busy) return
  editor.value.commands.insertContent(emoji.value)
  editor.value.commands.focus()
  emoji.value = ''
  capture('emoji_inserted_in_email', { emoji: emoji.value })
}

// Callable from outside (e.g. the command palette); setting the exposed ref
// from a parent doesn't write through to .value, so open via a method.
function openTemplateSelector() {
  showEmailTemplateSelectorModal.value = true
}

function toggleCC() {
  cc.value = !cc.value
  if (cc.value) nextTick(() => ccInput.value.setFocus())
}

function toggleBCC() {
  bcc.value = !bcc.value
  if (bcc.value) nextTick(() => bccInput.value.setFocus())
}

defineExpose({
  editor,
  showEmailTemplateSelectorModal,
  openTemplateSelector,
  subject,
  cc,
  bcc,
  fromEmail,
  replyAddresses,
  toEmails,
  ccEmails,
  bccEmails,
})
</script>
