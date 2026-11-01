<template>
  <EmailWorkspace
    v-if="doc.name && ['CRM Lead', 'CRM Deal'].includes(doctype)"
    ref="emailWorkspace"
    :reference-doctype="doctype"
    :reference-name="String(doc.name)"
    :default-recipient="doc.email || ''"
    @changed="reload = true"
  />
  <div class="flex justify-between gap-3 border-t px-4 py-2.5">
    <div class="flex gap-1.5">
      <Button
        variant="ghost"
        :class="[
          showEmailBox ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : '',
        ]"
        :label="__('Reply')"
        :iconLeft="Email2Icon"
        :disabled="emailBusy"
        @click="toggleEmailBox()"
      />
      <Button
        variant="ghost"
        :label="__('Comment')"
        :class="[
          showCommentBox ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : '',
        ]"
        :iconLeft="CommentIcon"
        :disabled="emailBusy"
        @click="toggleCommentBox()"
      />
    </div>
  </div>
  <div
    v-show="showEmailBox"
    @keydown.ctrl.enter.capture.stop.prevent="openSchedule"
    @keydown.meta.enter.capture.stop.prevent="openSchedule"
  >
    <fieldset :disabled="emailLocked" class="min-w-0">
      <EmailEditor
        ref="newEmailEditor"
        v-model:content="newEmail"
        v-model="doc"
        v-model:attachments="attachments"
        :submitButtonProps="{
          variant: 'solid',
          onClick: openSchedule,
          disabled: emailEmpty || emailBusy,
        }"
        :submit-label="__('Schedule')"
        :busy="emailLocked"
        :discardButtonProps="{
          disabled: emailBusy,
          onClick: async () => {
            await deleteAttachedFiles()
            showEmailBox = false
            newEmailEditor.subject = subject
            newEmailEditor.toEmails = doc.email ? [doc.email] : []
            newEmailEditor.ccEmails = []
            newEmailEditor.bccEmails = []
            newEmailEditor.cc = false
            newEmailEditor.bcc = false
            newEmail = ''
            showSchedule = false
            scheduleAttempt = null
          },
        }"
        :editable="showEmailBox && !emailLocked"
        :doctype="doctype"
        :subject="subject"
        :placeholder="
          __('Hi John, \n\nCan you please provide more details on this...')
        "
        @uploading="emailUploading = $event"
      >
        <template #secondary-actions>
          <Button
            :label="__('Send now')"
            :disabled="emailEmpty || emailBusy"
            @click="submitEmail"
          />
        </template>
      </EmailEditor>
    </fieldset>
    <form
      v-if="showSchedule"
      class="flex flex-col gap-3 border-t border-outline-gray-2 px-4 py-3"
      @submit.prevent="scheduleEmail"
    >
      <ScheduleFields
        v-model:wall="scheduleWall"
        v-model:timezone="scheduleTimezone"
        :disabled="emailBusy"
      />
      <label class="flex items-center gap-2 text-sm text-ink-gray-7">
        <input v-model="stopOnReply" type="checkbox" :disabled="emailBusy" />
        {{ __('Cancel if a new email arrives from this customer') }}
      </label>
      <p class="text-sm text-ink-gray-6">
        {{
          __('The email must reach CRM before sending to cancel the schedule.')
        }}
      </p>
      <p
        v-if="scheduleAttempt && !emailSending"
        role="status"
        class="text-sm text-ink-gray-7"
      >
        {{
          __(
            'The previous request may have succeeded. Retry scheduling to check its result before editing or sending again.',
          )
        }}
      </p>
      <p v-if="scheduleError" role="alert" class="text-sm text-ink-red-3">
        {{ scheduleError }}
      </p>
      <div class="flex gap-2">
        <Button
          type="submit"
          variant="solid"
          :label="
            scheduleAttempt ? __('Retry scheduling') : __('Schedule email')
          "
          :disabled="
            emailSending ||
            emailUploading ||
            (!scheduleAttempt && (emailEmpty || !scheduleWall))
          "
          :loading="emailSending"
        />
        <Button
          :label="__('Back to email')"
          :disabled="emailBusy"
          @click="showSchedule = false"
        />
      </div>
    </form>
  </div>
  <div
    v-show="showCommentBox"
    @keydown.ctrl.enter.capture.stop="submitComment"
    @keydown.meta.enter.capture.stop="submitComment"
  >
    <CommentBox
      ref="newCommentEditor"
      v-model:content="newComment"
      v-model="doc"
      v-model:attachments="attachments"
      :submitButtonProps="{
        variant: 'solid',
        onClick: submitComment,
        disabled: commentEmpty,
      }"
      :discardButtonProps="{
        onClick: async () => {
          await deleteAttachedFiles()
          showCommentBox = false
          newComment = ''
        },
      }"
      :editable="showCommentBox"
      :doctype="doctype"
      :placeholder="__('@John, can you please check this?')"
    />
  </div>
</template>

<script setup>
import EmailEditor from '@/components/EmailEditor.vue'
import EmailWorkspace from '@/components/EmailWorkspace/EmailWorkspace.vue'
import ScheduleFields from '@/components/EmailWorkspace/ScheduleFields.vue'
import { scheduleInstant, scheduleWallTime } from '@/utils/emailSchedule'
import CommentBox from '@/components/CommentBox.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import { isContentEmpty } from '@/utils'
import { usersStore } from '@/stores/users'
import { useStorage } from '@vueuse/core'
import { useOnboarding, useTelemetry } from 'frappe-ui/frappe'
import { call, createResource, toast } from 'frappe-ui'
import { ref, watch, computed, onMounted } from 'vue'

const props = defineProps({
  doctype: { type: String, default: 'CRM Lead' },
})

const doc = defineModel({ type: Object, default: () => ({}) })
const reload = defineModel('reload', { type: Boolean })

const emit = defineEmits(['scroll'])

const { getUser } = usersStore()
const { updateOnboardingStep } = useOnboarding('frappecrm')
const { capture } = useTelemetry()

const showEmailBox = ref(false)
const showCommentBox = ref(false)
const newEmail = useStorage(
  `emailBoxContent-${getUser().email}-${props.doctype}-${doc.value.name}`,
  '',
)
// A restored draft already carries its signature; this flag (persisted with the
// draft) stops setSignature from prepending another one on every reopen/reload.
const signatureAdded = useStorage(
  `emailSignatureAdded-${getUser().email}-${props.doctype}-${doc.value.name}`,
  false,
)
const newComment = useStorage(
  `commentBoxContent-${getUser().email}-${props.doctype}-${doc.value.name}`,
  '',
)
const newEmailEditor = ref(null)
const newCommentEditor = ref(null)
const emailWorkspace = ref(null)
const emailSending = ref(false)
const emailUploading = ref(false)
const emailLocked = computed(
  () => emailSending.value || !!scheduleAttempt.value,
)
const emailBusy = computed(() => emailLocked.value || emailUploading.value)
const showSchedule = ref(false)
const scheduleWall = ref('')
const scheduleTimezone = ref(
  getUser().time_zone ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    'UTC',
)
const stopOnReply = ref(true)
const scheduleError = ref('')
// Keep the key across a failed response or reload: retrying an uncertain result
// must retrieve the original scheduled email, rather than create a second one.
const scheduleAttempt = useStorage(
  `emailScheduleAttempt-${getUser().email}-${props.doctype}-${doc.value.name}`,
  null,
  localStorage,
  {
    serializer: { read: (value) => JSON.parse(value), write: JSON.stringify },
    flush: 'sync',
  },
)
if (scheduleAttempt.value) {
  const pending = JSON.parse(scheduleAttempt.value.snapshot)
  showEmailBox.value = showSchedule.value = true
  scheduleTimezone.value = pending.timezone
  scheduleWall.value = scheduleWallTime(pending.send_at, pending.timezone)
  stopOnReply.value = pending.data.stop_on_reply
}

const attachments = useStorage(
  `attachments-${getUser().email}-${props.doctype}-${doc.value.name}`,
  [],
  localStorage,
  {
    serializer: {
      read: (v) => (v ? JSON.parse(v) : []),
      write: (v) => JSON.stringify(v),
    },
  },
)

onMounted(() => {
  if (!scheduleAttempt.value) return
  const { data } = JSON.parse(scheduleAttempt.value.snapshot)
  newEmail.value = data.content
  attachments.value = data.attachments.map(
    (name) =>
      attachments.value.find((file) => file.name === name) || {
        name,
        file_name: name,
        file_url: name,
      },
  )
  const editor = newEmailEditor.value
  editor.subject = data.subject
  editor.fromEmail = data.sender
  editor.toEmails = data.recipients
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  editor.ccEmails = data.cc
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  editor.bccEmails = data.bcc
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  editor.cc = !!data.cc
  editor.bcc = !!data.bcc
})

const subject = computed(() => {
  let prefix = ''
  if (doc.value?.lead_name) {
    prefix = doc.value.lead_name
  } else if (doc.value?.organization) {
    prefix = doc.value.organization
  }
  return `${prefix} (#${doc.value.name})`
})

const signature = createResource({
  url: 'crm.api.get_user_signature',
  cache: 'user-email-signature',
  auto: true,
})

function setSignature(editor) {
  if (!signature.data || signatureAdded.value) return
  const sig = signature.data.replace(/\n/g, '<br>')
  let emailContent = editor.getHTML()
  emailContent = emailContent.startsWith('<p></p>')
    ? emailContent.slice(7)
    : emailContent
  editor.commands.setContent(sig + emailContent)
  editor.commands.focus('start')
  signatureAdded.value = true
}

// Clearing the draft (send / discard) resets the guard so the next fresh
// compose gets its signature again.
watch(newEmail, (value) => {
  if (!value) signatureAdded.value = false
})

watch(
  () => showEmailBox.value,
  (value) => {
    if (value) {
      let editor = newEmailEditor.value.editor
      editor.commands.focus()
      setSignature(editor)
    }
  },
)

watch(
  () => showCommentBox.value,
  (value) => {
    if (value) {
      newCommentEditor.value.editor.commands.focus()
    }
  },
)

const commentEmpty = computed(() => isContentEmpty(newComment.value))

const emailEmpty = computed(
  () =>
    isContentEmpty(newEmail.value) || !newEmailEditor.value?.toEmails?.length,
)

async function sendMail() {
  let fromEmail = newEmailEditor.value.fromEmail || getUser().email
  let recipients = newEmailEditor.value.toEmails
  let subject = newEmailEditor.value.subject
  let cc = newEmailEditor.value.ccEmails || []
  let bcc = newEmailEditor.value.bccEmails || []

  if (attachments.value.length) {
    capture('email_attachments_added')
  }
  await call('frappe.core.doctype.communication.email.make', {
    recipients: recipients.join(', '),
    attachments: attachments.value.map((x) => x.name),
    cc: cc.join(', '),
    bcc: bcc.join(', '),
    subject: subject,
    content: newEmail.value,
    doctype: props.doctype,
    name: doc.value.name,
    send_email: 1,
    sender: fromEmail,
    sender_full_name: getUser()?.full_name || undefined,
  })
}

async function sendComment() {
  let _attachments = attachments.value.length
    ? attachments.value.map((x) => x.name)
    : []

  let comment = await call('crm.api.comment.add_comment', {
    reference_doctype: props.doctype,
    reference_name: doc.value.name,
    content: newComment.value,
    attachments: _attachments,
  })

  if (comment && attachments.value.length) {
    capture('comment_attachments_added')
  }
}

async function deleteAttachedFiles() {
  if (!attachments.value || attachments.value.length === 0) return

  const deletePromises = attachments.value.map(async (file) => {
    try {
      await call('frappe.client.delete', {
        doctype: 'File',
        name: file.name,
      })
    } catch (error) {
      console.warn(`Failed to delete file ${file.name}:`, error)
    }
  })

  await Promise.all(deletePromises)

  attachments.value = []
}

async function submitEmail() {
  if (emailEmpty.value || emailBusy.value) return
  emailSending.value = true
  // toast.promise returns the toast id (not the promise), so await the send
  // itself — otherwise the reload below fires before the email is committed and
  // the new email is missing from the refetched list.
  const sending = sendMail()
  toast.promise(sending, {
    loading: __('Sending email...'),
    success: __('Email sent'),
    error: (e) => e?.messages?.[0] || __('Failed to send email!'),
  })
  try {
    await sending
  } catch {
    return
  } finally {
    emailSending.value = false
  }
  showEmailBox.value = false
  showSchedule.value = false
  scheduleAttempt.value = null
  newEmail.value = ''
  attachments.value = []
  reload.value = true
  emit('scroll')
  capture('email_sent', { doctype: props.doctype })
  updateOnboardingStep('send_first_email')
}

function openSchedule() {
  if (emailEmpty.value || emailBusy.value) return
  showSchedule.value = true
  scheduleError.value = ''
}

async function scheduleEmail() {
  if (
    emailSending.value ||
    emailUploading.value ||
    (!scheduleAttempt.value && emailEmpty.value)
  )
    return
  scheduleError.value = ''
  const target = doc.value.name
  let payload
  try {
    payload = scheduleAttempt.value
      ? JSON.parse(scheduleAttempt.value.snapshot)
      : {
          data: {
            reference_doctype: props.doctype,
            reference_name: target,
            sender: newEmailEditor.value.fromEmail || getUser().email,
            recipients: newEmailEditor.value.toEmails.join(', '),
            cc: (newEmailEditor.value.ccEmails || []).join(', '),
            bcc: (newEmailEditor.value.bccEmails || []).join(', '),
            subject: newEmailEditor.value.subject,
            content: newEmail.value,
            attachments: attachments.value.map((file) => file.name),
            stop_on_reply: stopOnReply.value,
          },
          send_at: scheduleInstant(scheduleWall.value, scheduleTimezone.value),
          timezone: scheduleTimezone.value,
        }
    const snapshot = JSON.stringify(payload)
    if (scheduleAttempt.value?.snapshot !== snapshot)
      scheduleAttempt.value = { snapshot, id: crypto.randomUUID() }
  } catch (error) {
    scheduleError.value = error.message
    return
  }
  emailSending.value = true
  try {
    const saved = await call('crm.api.scheduled_email.schedule_email', {
      ...payload,
      request_id: scheduleAttempt.value.id,
    })
    if (doc.value.name !== target) return
    emailWorkspace.value?.addScheduled(saved)
    newEmail.value = ''
    attachments.value = []
    showSchedule.value = showEmailBox.value = false
    scheduleWall.value = ''
    stopOnReply.value = true
    scheduleAttempt.value = null
    reload.value = true
    toast.success(
      saved.status === 'Scheduled'
        ? __('Email scheduled')
        : __('Email status: {0}', [__(saved.status)]),
    )
    emit('scroll')
  } catch (error) {
    if (error.exc_type && error.status >= 400 && error.status < 500)
      scheduleAttempt.value = null
    if (doc.value.name === target)
      scheduleError.value =
        error.messages?.join(' ') ||
        error.message ||
        __('Could not schedule email.')
  } finally {
    emailSending.value = false
  }
}

async function submitComment() {
  if (commentEmpty.value) return
  showCommentBox.value = false
  const sending = sendComment()
  toast.promise(sending, {
    loading: __('Sending comment...'),
    success: __('Comment sent'),
    error: (e) => e?.messages?.[0] || __('Failed to send comment!'),
  })
  try {
    await sending
  } catch {
    return
  }
  newComment.value = ''
  attachments.value = []
  reload.value = true
  emit('scroll')
  capture('comment_sent', { doctype: props.doctype })
  updateOnboardingStep('add_first_comment')
}

function toggleEmailBox() {
  if (emailBusy.value) return
  if (showCommentBox.value) {
    showCommentBox.value = false
  }
  showEmailBox.value = !showEmailBox.value
}

function toggleCommentBox() {
  if (emailBusy.value) return
  if (showEmailBox.value) {
    showEmailBox.value = false
  }
  showCommentBox.value = !showCommentBox.value
}

// Callable from outside (e.g. the command palette); setting the exposed ref
// from a parent doesn't write through to .value, so open via a method.
function openCommentBox() {
  if (emailBusy.value) return
  if (showEmailBox.value) showEmailBox.value = false
  showCommentBox.value = true
}

function openEmailBox() {
  if (emailBusy.value) return false
  if (showCommentBox.value) showCommentBox.value = false
  showEmailBox.value = true
  return true
}

defineExpose({
  show: showEmailBox,
  showComment: showCommentBox,
  editor: newEmailEditor,
  openCommentBox,
  openEmailBox,
})
</script>
