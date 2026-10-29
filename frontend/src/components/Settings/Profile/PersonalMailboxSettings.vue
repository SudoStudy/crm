<template>
  <SettingsLayoutBase :title="__('Connect your mailbox')">
    <template #content>
      <Button
        :label="__('Back to profile')"
        @click="emit('updateStep', 'profile-settings')"
      />
      <p class="mt-5 text-p-base text-ink-gray-6">
        {{
          __(
            'Connect your Google Workspace or Gmail mailbox to send and receive CRM emails from your own address.',
          )
        }}
      </p>
      <p v-if="loading" class="mt-4" role="status">
        {{ __('Loading mailbox settings…') }}
      </p>
      <form
        v-else-if="mailbox"
        class="mt-5 flex max-w-lg flex-col gap-4"
        @submit.prevent="connect"
      >
        <label class="flex flex-col gap-2 text-base-medium">
          {{ __('Your email address') }}
          <input
            class="form-input rounded border border-outline-gray-2 bg-surface-gray-1"
            :value="mailbox.email_id"
            readonly
            type="email"
          />
        </label>
        <p role="status" class="text-p-sm text-ink-gray-6">
          {{
            mailbox.connected
              ? __('This mailbox is connected.')
              : __('This mailbox is not connected yet.')
          }}
        </p>
        <template v-if="mailbox.can_manage">
          <label class="flex flex-col gap-2 text-base-medium">
            {{ __('Google app password') }}
            <input
              v-model="password"
              class="form-input rounded border border-outline-gray-2"
              type="password"
              autocomplete="new-password"
              required
              :disabled="saving"
            />
          </label>
          <p class="text-p-sm text-ink-gray-6">
            {{
              __(
                'Use a Google app password, not your normal sign-in password. Google requires two-step verification, and your Workspace administrator must allow app passwords.',
              )
            }}
            <a
              class="underline"
              href="https://support.google.com/accounts/answer/185833"
              target="_blank"
              rel="noopener noreferrer"
              >{{ __('Google setup instructions') }}</a
            >
          </p>
          <p class="text-p-sm text-ink-gray-6">
            {{
              __(
                'Only unread messages are synced. Connecting this mailbox will not automatically create contacts or leads.',
              )
            }}
          </p>
          <Button
            type="submit"
            variant="solid"
            :label="
              mailbox.connected
                ? __('Update connection')
                : __('Connect mailbox')
            "
            :loading="saving"
            :disabled="!password.trim() || saving"
          />
        </template>
        <p v-else class="text-p-sm text-ink-gray-6">
          {{
            __(
              'This mailbox is managed by an administrator or shared. Ask an administrator to update its connection.',
            )
          }}
        </p>
      </form>
      <p v-if="error" role="alert" class="mt-4 text-ink-red-4">{{ error }}</p>
      <p v-if="success" role="status" class="mt-4">
        {{ __('Your mailbox is connected and available for sending emails.') }}
      </p>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Button, call, getCachedDocumentResource } from 'frappe-ui'
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'

const emit = defineEmits(['updateStep'])
const mailbox = ref(null)
const password = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref(false)
let active = true
onBeforeUnmount(() => {
  active = false
  password.value = ''
})
onMounted(async () => {
  try {
    const data = await call('crm.api.personal_settings.get_personal_settings')
    if (active) mailbox.value = data.mailbox
  } catch {
    if (active)
      error.value = __(
        'Could not load your mailbox settings. Try again or contact an administrator.',
      )
  } finally {
    if (active) loading.value = false
  }
})
async function connect() {
  if (saving.value || !password.value.trim()) return
  saving.value = true
  error.value = ''
  success.value = false
  try {
    const result = await call(
      'crm.api.personal_settings.connect_personal_mailbox',
      {
        email_id: mailbox.value.email_id,
        password: password.value,
      },
    )
    if (active) {
      mailbox.value = result
      success.value = true
    }
    getCachedDocumentResource('User', result.email_id)?.reload()
  } catch {
    if (active)
      error.value = __(
        'Could not connect your mailbox. Check the Google app password and Workspace policy, or ask an administrator if the account is shared.',
      )
  } finally {
    password.value = ''
    if (active) saving.value = false
  }
}
</script>
