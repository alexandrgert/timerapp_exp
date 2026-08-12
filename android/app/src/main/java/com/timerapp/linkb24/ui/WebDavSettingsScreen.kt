package com.timerapp.linkb24.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.timerapp.linkb24.BuildConfig
import com.timerapp.linkb24.R
import com.timerapp.linkb24.webdav.REMIND_LATER_MINUTES_CHOICES

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WebDavSettingsScreen(
    onBack: () -> Unit,
    onSyncComplete: () -> Unit = {},
    viewModel: WebDavSettingsViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val exportLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument("application/json"),
    ) { uri ->
        if (uri == null) {
            return@rememberLauncherForActivityResult
        }
        runCatching {
            val payload = viewModel.exportSettingsJson()
            context.contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { writer ->
                writer.write(payload)
            } ?: error("Не удалось открыть файл")
            uri.lastPathSegment ?: "settings.json"
        }.onSuccess { name ->
            viewModel.markExportOk(name)
        }.onFailure { error ->
            viewModel.markExportFailed(error.message ?: "Не удалось экспортировать настройки")
        }
    }
    val importLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            viewModel.beginImportFromUri(uri)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.webdav_settings_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.back),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.webdav_settings_hint),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            SettingsCheckboxRow(
                label = stringResource(R.string.webdav_enabled),
                checked = uiState.enabled,
                onCheckedChange = viewModel::onEnabledChange,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = uiState.url,
                onValueChange = viewModel::onUrlChange,
                label = { Text(stringResource(R.string.webdav_url)) },
                placeholder = { Text(stringResource(R.string.webdav_url_placeholder)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = uiState.username,
                onValueChange = viewModel::onUsernameChange,
                label = { Text(stringResource(R.string.webdav_username)) },
                singleLine = true,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = uiState.password,
                onValueChange = viewModel::onPasswordChange,
                label = { Text(stringResource(R.string.webdav_password)) },
                singleLine = true,
                visualTransformation = if (uiState.showPassword) {
                    VisualTransformation.None
                } else {
                    PasswordVisualTransformation()
                },
                trailingIcon = {
                    IconButton(onClick = viewModel::toggleShowPassword) {
                        Icon(
                            imageVector = if (uiState.showPassword) {
                                Icons.Default.VisibilityOff
                            } else {
                                Icons.Default.Visibility
                            },
                            contentDescription = stringResource(
                                if (uiState.showPassword) {
                                    R.string.webdav_hide_password
                                } else {
                                    R.string.webdav_show_password
                                },
                            ),
                        )
                    }
                },
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = uiState.remotePath,
                onValueChange = viewModel::onRemotePathChange,
                label = { Text(stringResource(R.string.webdav_remote_path)) },
                placeholder = { Text(stringResource(R.string.webdav_remote_path_placeholder)) },
                singleLine = true,
            )

            SettingsCheckboxRow(
                label = stringResource(R.string.webdav_sync_on_startup),
                checked = uiState.syncOnStartup,
                onCheckedChange = viewModel::onSyncOnStartupChange,
            )

            SettingsCheckboxRow(
                label = stringResource(R.string.webdav_sync_on_shutdown),
                checked = uiState.syncOnShutdown,
                onCheckedChange = viewModel::onSyncOnShutdownChange,
            )

            SettingsCheckboxRow(
                label = stringResource(R.string.webdav_shutdown_upload_only),
                checked = uiState.shutdownUploadOnly,
                onCheckedChange = viewModel::onShutdownUploadOnlyChange,
            )

            Text(
                text = stringResource(R.string.webdav_upload_only_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = uiState.syncIntervalMinutes,
                onValueChange = viewModel::onSyncIntervalMinutesChange,
                label = { Text(stringResource(R.string.webdav_sync_interval_minutes)) },
                placeholder = { Text(stringResource(R.string.webdav_sync_interval_placeholder)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )

            Text(
                text = stringResource(R.string.webdav_sync_interval_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Text(
                text = stringResource(R.string.webdav_remind_later_minutes),
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                REMIND_LATER_MINUTES_CHOICES.forEach { minutes ->
                    FilterChip(
                        selected = uiState.syncRemindLaterMinutes == minutes,
                        onClick = { viewModel.onSyncRemindLaterMinutesChange(minutes) },
                        label = { Text("$minutes") },
                    )
                }
            }
            Text(
                text = stringResource(R.string.webdav_remind_later_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalButton(
                    onClick = viewModel::testConnection,
                    enabled = !uiState.isTesting && !uiState.isSaving && !uiState.isSyncing,
                ) {
                    Text(
                        if (uiState.isTesting) {
                            stringResource(R.string.webdav_testing)
                        } else {
                            stringResource(R.string.webdav_test)
                        },
                    )
                }
                FilledTonalButton(
                    onClick = { viewModel.save() },
                    enabled = !uiState.isTesting && !uiState.isSaving && !uiState.isSyncing,
                ) {
                    Text(
                        if (uiState.isSaving) {
                            stringResource(R.string.webdav_saving)
                        } else {
                            stringResource(R.string.webdav_save)
                        },
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalButton(
                    onClick = { viewModel.pullNow(onSyncComplete) },
                    enabled = !uiState.isTesting && !uiState.isSaving && !uiState.isSyncing,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(
                        if (uiState.isSyncing) {
                            stringResource(R.string.webdav_syncing)
                        } else {
                            stringResource(R.string.webdav_pull)
                        },
                    )
                }
                FilledTonalButton(
                    onClick = { viewModel.pushNow(onSyncComplete) },
                    enabled = !uiState.isTesting && !uiState.isSaving && !uiState.isSyncing,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.webdav_push))
                }
            }

            FilledTonalButton(
                onClick = viewModel::openLog,
                enabled = !uiState.isTesting && !uiState.isSaving && !uiState.isSyncing,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.webdav_log))
            }

            uiState.statusMessage?.let { message ->
                Text(message, style = MaterialTheme.typography.bodySmall)
            }

            uiState.savedMessage?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.primary)
            }

            uiState.errorMessage?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.error)
            }

            Text(
                text = stringResource(R.string.app_section_title),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = stringResource(
                    R.string.app_version_format,
                    BuildConfig.VERSION_NAME,
                    BuildConfig.VERSION_CODE,
                ),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            SettingsCheckboxRow(
                label = stringResource(R.string.check_updates),
                checked = uiState.checkUpdates,
                onCheckedChange = viewModel::onCheckUpdatesChange,
            )
            OutlinedTextField(
                value = uiState.updateGithubRepo,
                onValueChange = viewModel::onUpdateGithubRepoChange,
                label = { Text(stringResource(R.string.update_github_repo)) },
                placeholder = { Text(stringResource(R.string.update_github_repo_placeholder)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                text = stringResource(R.string.update_github_repo_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = uiState.updateCheckIntervalDays,
                onValueChange = viewModel::onUpdateCheckIntervalDaysChange,
                label = { Text(stringResource(R.string.update_check_interval_days)) },
                enabled = uiState.checkUpdates,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                text = stringResource(R.string.update_check_interval_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            FilledTonalButton(
                onClick = viewModel::checkUpdatesNow,
                enabled = !uiState.isCheckingUpdates,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    if (uiState.isCheckingUpdates) {
                        stringResource(R.string.update_checking)
                    } else {
                        stringResource(R.string.update_check_now)
                    },
                )
            }
            uiState.updateStatusMessage?.let { message ->
                Text(message, style = MaterialTheme.typography.bodySmall)
            }
            if (!uiState.updateReleaseUrl.isNullOrBlank()) {
                TextButton(onClick = viewModel::openUpdateRelease) {
                    Text(stringResource(R.string.update_open_release))
                }
            }
            Text(
                text = stringResource(R.string.app_update_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Text(
                text = stringResource(R.string.settings_io_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalButton(
                    onClick = { exportLauncher.launch("timerapp-settings.json") },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.settings_export))
                }
                FilledTonalButton(
                    onClick = { importLauncher.launch(arrayOf("application/json", "text/*", "*/*")) },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.settings_import))
                }
            }
            uiState.settingsIoMessage?.let { message ->
                Text(message, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }

    if (uiState.pendingImportConfirmStep == 1) {
        AlertDialog(
            onDismissRequest = viewModel::cancelImportConfirm,
            title = { Text(stringResource(R.string.settings_import_confirm_title)) },
            text = { Text(stringResource(R.string.settings_import_confirm_1)) },
            confirmButton = {
                TextButton(onClick = viewModel::advanceImportConfirm) {
                    Text(stringResource(R.string.yes))
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::cancelImportConfirm) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }
    if (uiState.pendingImportConfirmStep == 2) {
        AlertDialog(
            onDismissRequest = viewModel::cancelImportConfirm,
            title = { Text(stringResource(R.string.settings_import_confirm_title_2)) },
            text = { Text(stringResource(R.string.settings_import_confirm_2)) },
            confirmButton = {
                TextButton(onClick = viewModel::advanceImportConfirm) {
                    Text(stringResource(R.string.yes))
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::cancelImportConfirm) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }

    if (uiState.showLogDialog) {
        AlertDialog(
            onDismissRequest = viewModel::dismissLog,
            title = { Text(stringResource(R.string.webdav_log_title)) },
            text = {
                Column {
                    Text(
                        text = stringResource(R.string.webdav_log_hint),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = uiState.logText,
                        style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(280.dp)
                            .verticalScroll(rememberScrollState()),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = viewModel::refreshLog) {
                    Text(stringResource(R.string.webdav_log_refresh))
                }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = viewModel::clearLog) {
                        Text(stringResource(R.string.webdav_log_clear))
                    }
                    TextButton(onClick = viewModel::dismissLog) {
                        Text(stringResource(R.string.close))
                    }
                }
            },
        )
    }
}

@Composable
private fun SettingsCheckboxRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = onCheckedChange)
        Text(
            text = label,
            modifier = Modifier.padding(start = 8.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}
