package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const agentVersion = "0.4.1"

type Config struct {
	BackendURL string
	Token      string
	MachineID  string
	Hostname   string
	StateDir   string
}
type Command struct {
	ID            int    `json:"id"`
	Type          string `json:"type"`
	ExamID        string `json:"exam_id"`
	AssignmentID  int    `json:"assignment_id"`
	StudentNumber string `json:"student_number"`
	MachineID     string `json:"machine_id"`
}
type CommandResponse struct {
	Command *Command `json:"command"`
}
type ExamConfig struct {
	ExamID   string `json:"exam_id"`
	Filename string `json:"filename"`
	Content  string `json:"content"`
}

func main() {
	if runtime.GOOS == "linux" {
		if err := configureSystemPath(); err != nil {
			log.Fatalf("PATH NixOS: %v", err)
		}
	}
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("SecureExam Agent %s", agentVersion)
	log.Printf("machine_id = %s", cfg.MachineID)
	log.Printf("backend    = %s", cfg.BackendURL)
	log.Printf("os         = %s/%s", runtime.GOOS, runtime.GOARCH)
	err = postJSON(
		cfg,
		"/agent/register",
		map[string]any{
			"machine_id": cfg.MachineID,
			"hostname":   cfg.Hostname,
			"os_name":    runtime.GOOS,
			"version":    agentVersion,
		},
		nil,
	)
	if err != nil {
		log.Fatalf("register: %v", err)
	}
	state := "IDLE"
	log.Printf("state -> %s", state)
	for {
		if err := heartbeat(cfg, state); err != nil {
			log.Printf("heartbeat error: %v", err)
		}
		var response CommandResponse
		err := getJSON(
			cfg,
			"/agent/commands/"+cfg.MachineID+"/next",
			&response,
		)
		if err != nil {
			log.Printf("poll error: %v", err)
			time.Sleep(3 * time.Second)
			continue
		}
		if response.Command == nil {
			time.Sleep(3 * time.Second)
			continue
		}
		cmd := response.Command
		log.Printf(
			"command #%d -> %s exam=%s student=%s",
			cmd.ID,
			cmd.Type,
			cmd.ExamID,
			cmd.StudentNumber,
		)
		switch cmd.Type {
		case "START_EXAM":
			state = processStartExam(cfg, cmd)
		case "END_EXAM":
			state = processEndExam(cfg, cmd)
		default:
			_ = complete(cfg, cmd.ID, "ERROR", "Commande inconnue")
			state = "ERROR"
		}
	}
}
func processStartExam(
	cfg Config,
	cmd *Command,
) string {
	// Linux starts with RESET, before fetching or building the new exam.
	if runtime.GOOS == "linux" {
		if os.Geteuid() != 0 {
			return failCommand(cfg, cmd.ID, errors.New("START_EXAM doit etre execute en root"))
		}
		setState(cfg, "RESETTING")
		if err := resetBeforeStart(cfg, cmd); err != nil {
			return failCommand(cfg, cmd.ID, fmt.Errorf("reset avant examen: %w", err))
		}
	}

	setState(
		cfg,
		"CHECKING",
	)
	var examConfig ExamConfig
	err := getJSON(
		cfg,
		"/agent/config/"+cmd.ExamID,
		&examConfig,
	)
	if err != nil {
		return failCommand(
			cfg,
			cmd.ID,
			fmt.Errorf(
				"telechargement config: %w",
				err,
			),
		)
	}
	if strings.TrimSpace(
		examConfig.Content,
	) == "" {
		return failCommand(
			cfg,
			cmd.ID,
			errors.New(
				"configuration NixOS vide",
			),
		)
	}
	log.Printf(
		"config received: %s (%d bytes)",
		examConfig.Filename,
		len(examConfig.Content),
	)
	setState(
		cfg,
		"PREPARING",
	)
	if runtime.GOOS != "linux" {
		log.Printf(
			"Windows dev mode: simulation uniquement",
		)
		time.Sleep(
			1 * time.Second,
		)
		err = complete(
			cfg,
			cmd.ID,
			"DONE",
			"SIMULATED_READY",
		)
		if err != nil {
			log.Printf(
				"complete error: %v",
				err,
			)
			return "ERROR"
		}
		log.Printf(
			"state -> READY",
		)
		log.Printf(
			"exam %s READY (simulation Windows)",
			cmd.ExamID,
		)
		return "READY"
	}
	// =====================================================
	// VRAI MODE NIXOS
	// =====================================================
	if os.Geteuid() != 0 {
		return failCommand(
			cfg,
			cmd.ID,
			errors.New(
				"l'agent Linux doit etre execute en root",
			),
		)
	}
	setState(
		cfg,
		"PREPARING",
	)
	err = prepareNixOSExam(
		cfg,
		cmd,
		examConfig.Content,
	)
	if err != nil {
		return failCommand(
			cfg,
			cmd.ID,
			err,
		)
	}
	setState(
		cfg,
		"SWITCHING",
	)
	err = switchNixOSExam(
		cfg,
		cmd,
	)
	if err != nil {
		log.Printf(
			"switch failed: %v",
			err,
		)
		log.Printf(
			"rollback -> tentative restauration systeme precedent",
		)
		rollbackErr := restoreBaseline(
			cfg,
			cmd,
		)
		if rollbackErr != nil {
			log.Printf(
				"ROLLBACK ERROR: %v",
				rollbackErr,
			)
		} else {
			log.Printf(
				"rollback systeme OK",
			)
		}
		return failCommand(
			cfg,
			cmd.ID,
			err,
		)
	}
	err = verifyNixOSExam(
		cfg,
		cmd,
	)
	if err != nil {
		log.Printf(
			"verification failed: %v",
			err,
		)
		rollbackErr := restoreBaseline(
			cfg,
			cmd,
		)
		if rollbackErr != nil {
			log.Printf(
				"ROLLBACK ERROR: %v",
				rollbackErr,
			)
		}
		return failCommand(
			cfg,
			cmd.ID,
			err,
		)
	}
	if err := prepareCleanWorkspace(); err != nil {
		rollbackErr := restoreBaseline(cfg, cmd)
		return failCommand(cfg, cmd.ID, fmt.Errorf("workspace: %v; rollback: %v", err, rollbackErr))
	}
	err = complete(
		cfg,
		cmd.ID,
		"DONE",
		"NIXOS_READY",
	)
	if err != nil {
		log.Printf(
			"complete error: %v",
			err,
		)
		return "ERROR"
	}
	log.Printf(
		"state -> READY",
	)
	log.Printf(
		"exam %s READY on NixOS",
		cmd.ExamID,
	)
	return "READY"
}

type PendingSubmission struct {
	AssignmentID int    `json:"assignment_id"`
	CommandID    int    `json:"command_id"`
	ArchivePath  string `json:"archive_path"`
	Uploaded     bool   `json:"uploaded"`
}

func processEndExam(cfg Config, cmd *Command) string {
	setState(cfg, "COLLECTING")
	if runtime.GOOS != "linux" {
		if err := complete(cfg, cmd.ID, "DONE", "SIMULATED_END"); err != nil {
			return "ERROR"
		}
		return "IDLE"
	}
	if os.Geteuid() != 0 {
		return failCommand(cfg, cmd.ID, errors.New("END_EXAM doit etre execute en root"))
	}
	baseline, err := readPermanentBaseline(cfg)
	if err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	pendingPath := filepath.Join(cfg.StateDir, "pending-submission")
	pending := PendingSubmission{AssignmentID: cmd.AssignmentID, CommandID: cmd.ID}
	data, err := os.ReadFile(pendingPath)
	if err == nil {
		if err := json.Unmarshal(data, &pending); err != nil {
			return failCommand(cfg, cmd.ID, err)
		}
		if pending.AssignmentID != cmd.AssignmentID {
			return failCommand(cfg, cmd.ID, errors.New("un autre assignment attend la fin de soumission"))
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return failCommand(cfg, cmd.ID, err)
	}
	save := func() error {
		data, err := json.Marshal(pending)
		if err != nil {
			return err
		}
		return atomicWrite(pendingPath, data, 0600)
	}
	// Persist before collecting; END retries resume the SAME archive rather
	// than uploading an empty workspace after a reset or lost acknowledgement.
	if err := save(); err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	if !pending.Uploaded {
		if pending.ArchivePath == "" {
			if err := stopExamProcesses(); err != nil {
				return failCommand(cfg, cmd.ID, err)
			}
			archivePath, err := createWorkspaceArchive(cfg, cmd)
			if err != nil {
				return failCommand(cfg, cmd.ID, err)
			}
			pending.ArchivePath = archivePath
			if err := save(); err != nil {
				return failCommand(cfg, cmd.ID, err)
			}
		}
		if filepath.Dir(pending.ArchivePath) != filepath.Join(cfg.StateDir, "archives") {
			return failCommand(cfg, cmd.ID, errors.New("chemin archive en attente invalide"))
		}
		setState(cfg, "UPLOADING")
		if err := uploadSubmission(cfg, cmd, pending.ArchivePath); err != nil {
			log.Printf("upload failed -> workspace and archive preserved; START blocked")
			return failCommand(cfg, cmd.ID, fmt.Errorf("upload rendu: %w", err))
		}
		pending.Uploaded = true
		if err := save(); err != nil {
			return failCommand(cfg, cmd.ID, err)
		}
		log.Printf("submission upload OK")
	}
	setState(cfg, "RESETTING")
	if err := stopExamProcesses(); err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	if err := restoreBaselinePath(baseline); err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	if err := cleanWorkspace("/home/exam/workspace"); err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	uploadedDir := filepath.Join(cfg.StateDir, "uploaded")
	if err := os.MkdirAll(uploadedDir, 0700); err != nil {
		return failCommand(cfg, cmd.ID, err)
	}
	dest := filepath.Join(uploadedDir, fmt.Sprintf("command-%d-%s", pending.CommandID, filepath.Base(pending.ArchivePath)))
	if err := os.Rename(pending.ArchivePath, dest); err != nil {
		// The previous attempt may already have moved the uploaded copy.
		if !errors.Is(err, os.ErrNotExist) {
			return failCommand(cfg, cmd.ID, err)
		}
		if _, err := os.Stat(dest); err != nil {
			return failCommand(cfg, cmd.ID, err)
		}
	}
	if err := complete(cfg, cmd.ID, "DONE", "SUBMITTED_RESET_DONE"); err != nil {
		log.Printf("complete END_EXAM error: %v; uploaded archive retained", err)
		return "ERROR"
	}
	if err := os.Remove(pendingPath); err != nil {
		log.Printf("pending marker cleanup failed: %v", err)
		return "ERROR"
	}
	log.Printf("END_EXAM DONE: baseline and workspace reset")
	return "IDLE"
}

func findBaselineForAssignment(cfg Config, assignmentID int) (string, error) {
	pattern := filepath.Join(
		cfg.StateDir,
		"runtime",
		fmt.Sprintf("assignment-%d-command-*", assignmentID),
		"baseline-system",
	)
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return "", err
	}
	if len(matches) == 0 {
		return "", fmt.Errorf("baseline introuvable pour assignment %d", assignmentID)
	}
	var selected string
	var selectedTime time.Time
	for _, candidate := range matches {
		info, err := os.Stat(candidate)
		if err != nil {
			continue
		}
		if selected == "" || info.ModTime().After(selectedTime) {
			selected = candidate
			selectedTime = info.ModTime()
		}
	}
	if selected == "" {
		return "", errors.New("baseline lisible introuvable")
	}
	data, err := os.ReadFile(selected)
	if err != nil {
		return "", err
	}
	baseline := strings.TrimSpace(string(data))
	if !strings.HasPrefix(baseline, "/nix/store/") {
		return "", fmt.Errorf("baseline invalide: %s", baseline)
	}
	return baseline, nil
}
func restoreBaselinePath(baseline string) error {
	if err := validateBaseline(baseline); err != nil {
		return err
	}
	// Reset the boot profile too. switch-to-configuration alone only restores
	// the running system and can leave the exam profile selected at reboot.
	profile, err := filepath.EvalSymlinks(systemProfilePath)
	if err != nil || profile != baseline {
		if _, err := runCommand("/", "nix-env", "--profile", systemProfilePath, "--set", baseline); err != nil {
			return err
		}
	}
	current, err := filepath.EvalSymlinks(currentSystemPath)
	if err != nil || current != baseline {
		output, err := runCommand("/", filepath.Join(baseline, "bin", "switch-to-configuration"), "switch")
		if output != "" {
			log.Printf("rollback: %s", output)
		}
		if err != nil {
			return fmt.Errorf("rollback systeme: %w", err)
		}
	}
	current, err = filepath.EvalSymlinks(currentSystemPath)
	if err != nil || current != baseline {
		return fmt.Errorf("reset non confirme: actif=%s attendu=%s: %v", current, baseline, err)
	}
	profile, err = filepath.EvalSymlinks(systemProfilePath)
	if err != nil || profile != baseline {
		return fmt.Errorf("profil de boot non restaure: %s: %v", profile, err)
	}
	log.Printf("RESET baseline verified = %s", baseline)
	return nil
}

func cleanWorkspace(workspace string) error {
	if err := validateWorkspace(workspace); err != nil {
		return err
	}
	entries, err := os.ReadDir(workspace)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if err := os.RemoveAll(filepath.Join(workspace, entry.Name())); err != nil {
			return err
		}
	}
	remaining, err := os.ReadDir(workspace)
	if err != nil {
		return err
	}
	if len(remaining) != 0 {
		return errors.New("workspace non vide apres nettoyage")
	}
	return nil
}

func safeArchiveComponent(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "unknown"
	}
	var result strings.Builder
	for _, c := range value {
		if (c >= 'a' && c <= 'z') ||
			(c >= 'A' && c <= 'Z') ||
			(c >= '0' && c <= '9') ||
			c == '-' || c == '_' || c == '.' {
			result.WriteRune(c)
		} else {
			result.WriteRune('_')
		}
	}
	cleaned := strings.Trim(result.String(), "._-")
	if cleaned == "" {
		return "unknown"
	}
	return cleaned
}
func createWorkspaceArchive(cfg Config, cmd *Command) (string, error) {
	const workspace = "/home/exam/workspace"
	if err := validateWorkspace(workspace); err != nil {
		return "", err
	}
	info, err := os.Stat(workspace)
	if err != nil {
		return "", fmt.Errorf("workspace inaccessible: %w", err)
	}
	if !info.IsDir() {
		return "", errors.New("workspace invalide")
	}
	archiveDir := filepath.Join(cfg.StateDir, "archives")
	if err := os.MkdirAll(archiveDir, 0700); err != nil {
		return "", err
	}
	filename := fmt.Sprintf(
		"%s_%s_assignment-%d.zip",
		safeArchiveComponent(cmd.ExamID),
		safeArchiveComponent(cmd.StudentNumber),
		cmd.AssignmentID,
	)
	archivePath := filepath.Join(archiveDir, filename)
	file, err := os.OpenFile(archivePath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return "", err
	}
	zipWriter := zip.NewWriter(file)
	walkErr := filepath.Walk(workspace, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == workspace {
			return nil
		}
		if info.Mode()&os.ModeSymlink != 0 {
			log.Printf("skip symlink: %s", path)
			return nil
		}
		relative, err := filepath.Rel(workspace, path)
		if err != nil {
			return err
		}
		header, err := zip.FileInfoHeader(info)
		if err != nil {
			return err
		}
		header.Name = filepath.ToSlash(relative)
		if info.IsDir() {
			header.Name += "/"
			_, err = zipWriter.CreateHeader(header)
			return err
		}
		if !info.Mode().IsRegular() {
			return nil
		}
		header.Method = zip.Deflate
		target, err := zipWriter.CreateHeader(header)
		if err != nil {
			return err
		}
		source, err := os.Open(path)
		if err != nil {
			return err
		}
		_, copyErr := io.Copy(target, source)
		closeErr := source.Close()
		if copyErr != nil {
			return copyErr
		}
		return closeErr
	})
	closeZipErr := zipWriter.Close()
	closeFileErr := file.Close()
	if walkErr != nil {
		_ = os.Remove(archivePath)
		return "", walkErr
	}
	if closeZipErr != nil {
		_ = os.Remove(archivePath)
		return "", closeZipErr
	}
	if closeFileErr != nil {
		_ = os.Remove(archivePath)
		return "", closeFileErr
	}
	return archivePath, nil
}
func uploadSubmission(cfg Config, cmd *Command, archivePath string) error {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	fields := map[string]string{
		"exam_id":    cmd.ExamID,
		"student_id": cmd.StudentNumber,
		"machine_id": cfg.MachineID,
	}
	for key, value := range fields {
		if err := writer.WriteField(key, value); err != nil {
			return err
		}
	}
	part, err := writer.CreateFormFile("archive", filepath.Base(archivePath))
	if err != nil {
		return err
	}
	source, err := os.Open(archivePath)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(part, source)
	closeErr := source.Close()
	if copyErr != nil {
		return copyErr
	}
	if closeErr != nil {
		return closeErr
	}
	if err := writer.Close(); err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPost, cfg.BackendURL+"/submissions", &body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("X-SecureExam-Agent-Token", cfg.Token)
	req.Header.Set("ngrok-skip-browser-warning", "1")
	client := &http.Client{Timeout: 2 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	log.Printf("upload response: %s", strings.TrimSpace(string(responseBody)))
	return nil
}
func prepareNixOSExam(
	cfg Config,
	cmd *Command,
	content string,
) error {
	runtimeDir := examRuntimeDir(
		cfg,
		cmd,
	)
	err := os.MkdirAll(
		runtimeDir,
		0700,
	)
	if err != nil {
		return fmt.Errorf(
			"creation runtime dir: %w",
			err,
		)
	}
	// -----------------------------------------------------
	// Sauvegarder le systeme NixOS EXACT actuellement actif.
	// -----------------------------------------------------
	baseline, err := readPermanentBaseline(cfg)
	if err != nil {
		return err
	}
	current, err := filepath.EvalSymlinks(currentSystemPath)
	if err != nil || current != baseline {
		return fmt.Errorf("preparation refusee: baseline non active (%s): %v", current, err)
	}
	baselineFile := filepath.Join(
		runtimeDir,
		"baseline-system",
	)
	err = atomicWrite(
		baselineFile,
		[]byte(
			baseline+"\n",
		),
		0600,
	)
	if err != nil {
		return fmt.Errorf(
			"sauvegarde baseline: %w",
			err,
		)
	}
	log.Printf(
		"baseline system = %s",
		baseline,
	)
	// -----------------------------------------------------
	// Ecrire le module genere par SecureExam.
	// -----------------------------------------------------
	modulePath := filepath.Join(
		runtimeDir,
		"exam-module.nix",
	)
	err = atomicWrite(
		modulePath,
		[]byte(content),
		0600,
	)
	if err != nil {
		return fmt.Errorf(
			"ecriture module Nix: %w",
			err,
		)
	}
	// -----------------------------------------------------
	// Wrapper :
	// - conserve configuration.nix de la machine
	// - desactive l'ancien module exam.nix fixe
	// - ajoute le module genere par le backend
	// -----------------------------------------------------
	wrapper := fmt.Sprintf(
		`{ config, pkgs, lib, ... }:
{
  disabledModules = [
    /etc/nixos/secureexam/exam.nix
  ];
  imports = [
    /etc/nixos/configuration.nix
    %s
  ];
}
`,
		modulePath,
	)
	wrapperPath := filepath.Join(
		runtimeDir,
		"configuration.nix",
	)
	err = atomicWrite(
		wrapperPath,
		[]byte(wrapper),
		0600,
	)
	if err != nil {
		return fmt.Errorf(
			"ecriture wrapper Nix: %w",
			err,
		)
	}
	log.Printf(
		"validating generated Nix module",
	)
	_, err = runCommand(
		runtimeDir,
		"nix-instantiate",
		"--parse",
		modulePath,
	)
	if err != nil {
		return fmt.Errorf(
			"validation exam-module.nix: %w",
			err,
		)
	}
	_, err = runCommand(
		runtimeDir,
		"nix-instantiate",
		"--parse",
		wrapperPath,
	)
	if err != nil {
		return fmt.Errorf(
			"validation configuration.nix: %w",
			err,
		)
	}
	log.Printf(
		"Nix syntax OK",
	)
	// -----------------------------------------------------
	// PRE-BUILD.
	//
	// Rien n'est encore applique au systeme.
	// -----------------------------------------------------
	log.Printf(
		"nixos-rebuild build...",
	)
	output, err := runCommand(
		runtimeDir,
		"nixos-rebuild",
		"build",
		"-I",
		"nixos-config="+wrapperPath,
	)
	if output != "" {
		log.Printf(
			"build: %s",
			output,
		)
	}
	if err != nil {
		return fmt.Errorf(
			"nixos-rebuild build: %w",
			err,
		)
	}
	log.Printf(
		"NixOS build OK",
	)
	return nil
}
func switchNixOSExam(
	cfg Config,
	cmd *Command,
) error {
	runtimeDir := examRuntimeDir(
		cfg,
		cmd,
	)
	wrapperPath := filepath.Join(
		runtimeDir,
		"configuration.nix",
	)
	log.Printf(
		"nixos-rebuild switch...",
	)
	output, err := runCommand(
		runtimeDir,
		"nixos-rebuild",
		"switch",
		"-I",
		"nixos-config="+wrapperPath,
	)
	if output != "" {
		log.Printf(
			"switch: %s",
			output,
		)
	}
	if err != nil {
		return fmt.Errorf(
			"nixos-rebuild switch: %w",
			err,
		)
	}
	log.Printf(
		"NixOS switch OK",
	)
	return nil
}
func verifyNixOSExam(
	cfg Config,
	cmd *Command,
) error {
	current, err := filepath.EvalSymlinks(
		"/run/current-system",
	)
	if err != nil {
		return fmt.Errorf(
			"verification current-system: %w",
			err,
		)
	}
	if !strings.HasPrefix(
		current,
		"/nix/store/",
	) {
		return fmt.Errorf(
			"current system invalide: %s",
			current,
		)
	}
	log.Printf(
		"current system = %s",
		current,
	)
	// Le compte exam fait partie de notre environnement
	// SecureExam actuel.
	_, err = runCommand(
		"/",
		"id",
		"exam",
	)
	if err != nil {
		return fmt.Errorf(
			"verification utilisateur exam: %w",
			err,
		)
	}
	log.Printf(
		"verification exam user OK",
	)
	return nil
}
func restoreBaseline(cfg Config, cmd *Command) error {
	baseline, err := readPermanentBaseline(cfg)
	if err != nil {
		return err
	}
	return restoreBaselinePath(baseline)
}

func examRuntimeDir(
	cfg Config,
	cmd *Command,
) string {
	return filepath.Join(
		cfg.StateDir,
		"runtime",
		fmt.Sprintf(
			"assignment-%d-command-%d",
			cmd.AssignmentID,
			cmd.ID,
		),
	)
}
func atomicWrite(
	path string,
	data []byte,
	mode os.FileMode,
) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(
		dir,
		0700,
	); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(
		tmp,
		data,
		mode,
	); err != nil {
		return err
	}
	if err := os.Chmod(
		tmp,
		mode,
	); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if err := os.Rename(
		tmp,
		path,
	); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}
func runCommand(
	dir string,
	name string,
	args ...string,
) (string, error) {
	path, err := exec.LookPath(name)
	if err != nil {
		return "", fmt.Errorf(
			"%s introuvable dans PATH",
			name,
		)
	}
	cmd := exec.Command(
		path,
		args...,
	)
	cmd.Dir = dir
	cmd.Env = append(
		os.Environ(),
		"NIXOS_CONFIG=",
	)
	output, err := cmd.CombinedOutput()
	text := strings.TrimSpace(
		string(output),
	)
	if len(text) > 20000 {
		text = text[len(text)-20000:]
	}
	if err != nil {
		return text, fmt.Errorf(
			"%s %s: %v\n%s",
			name,
			strings.Join(args, " "),
			err,
			text,
		)
	}
	return text, nil
}
func failCommand(
	cfg Config,
	commandID int,
	err error,
) string {
	log.Printf(
		"ERROR: %v",
		err,
	)
	completeErr := complete(
		cfg,
		commandID,
		"ERROR",
		err.Error(),
	)
	if completeErr != nil {
		log.Printf(
			"complete ERROR failed: %v",
			completeErr,
		)
	}
	log.Printf(
		"state -> ERROR",
	)
	_ = heartbeat(
		cfg,
		"ERROR",
	)
	return "ERROR"
}
func setState(
	cfg Config,
	state string,
) {
	log.Printf(
		"state -> %s",
		state,
	)
	if err := heartbeat(
		cfg,
		state,
	); err != nil {
		log.Printf(
			"heartbeat %s error: %v",
			state,
			err,
		)
	}
}
func loadConfig() (Config, error) {
	backend := strings.TrimRight(
		strings.TrimSpace(
			os.Getenv(
				"SECUREEXAM_BACKEND_URL",
			),
		),
		"/",
	)
	if backend == "" {
		backend = "http://127.0.0.1:8000"
	}
	token := strings.TrimSpace(
		os.Getenv(
			"SECUREEXAM_AGENT_TOKEN",
		),
	)
	if token == "" {
		return Config{},
			errors.New(
				"SECUREEXAM_AGENT_TOKEN manquant",
			)
	}
	machineID := strings.TrimSpace(
		os.Getenv(
			"SECUREEXAM_MACHINE_ID",
		),
	)
	if machineID == "" {
		machineID = detectMachineID()
	}
	if machineID == "" {
		return Config{},
			errors.New(
				"machine_id introuvable",
			)
	}
	hostname, _ := os.Hostname()
	stateDir := strings.TrimSpace(
		os.Getenv(
			"SECUREEXAM_STATE_DIR",
		),
	)
	if stateDir == "" {
		if runtime.GOOS == "linux" {
			stateDir =
				"/var/lib/secureexam-agent"
		} else {
			stateDir =
				filepath.Join(
					os.TempDir(),
					"secureexam-agent",
				)
		}
	}
	return Config{
		BackendURL: backend,
		Token:      token,
		MachineID:  machineID,
		Hostname:   hostname,
		StateDir:   stateDir,
	}, nil
}
func detectMachineID() string {
	if runtime.GOOS == "linux" {
		data, err := os.ReadFile(
			"/etc/machine-id",
		)
		if err == nil {
			value := strings.TrimSpace(
				string(data),
			)
			if value != "" {
				return value
			}
		}
	}
	hostname, _ := os.Hostname()
	hostname = strings.TrimSpace(
		hostname,
	)
	if hostname == "" {
		return ""
	}
	return "DEV-" +
		strings.ToUpper(
			hostname,
		)
}
func heartbeat(
	cfg Config,
	state string,
) error {
	return postJSON(
		cfg,
		"/agent/heartbeat",
		map[string]any{
			"machine_id": cfg.MachineID,
			"state":      state,
		},
		nil,
	)
}
func complete(
	cfg Config,
	commandID int,
	status string,
	message string,
) error {
	return postJSON(
		cfg,
		fmt.Sprintf(
			"/agent/commands/%d/complete",
			commandID,
		),
		map[string]any{
			"machine_id": cfg.MachineID,
			"status":     status,
			"message":    message,
		},
		nil,
	)
}
func getJSON(
	cfg Config,
	path string,
	out any,
) error {
	req, err := http.NewRequest(
		http.MethodGet,
		cfg.BackendURL+path,
		nil,
	)
	if err != nil {
		return err
	}
	return execute(
		cfg,
		req,
		out,
	)
}
func postJSON(
	cfg Config,
	path string,
	body any,
	out any,
) error {
	payload, err := json.Marshal(
		body,
	)
	if err != nil {
		return err
	}
	req, err := http.NewRequest(
		http.MethodPost,
		cfg.BackendURL+path,
		bytes.NewReader(
			payload,
		),
	)
	if err != nil {
		return err
	}
	req.Header.Set(
		"Content-Type",
		"application/json",
	)
	return execute(
		cfg,
		req,
		out,
	)
}
func execute(
	cfg Config,
	req *http.Request,
	out any,
) error {
	req.Header.Set(
		"X-SecureExam-Agent-Token",
		cfg.Token,
	)
	req.Header.Set(
		"ngrok-skip-browser-warning",
		"1",
	)
	client := &http.Client{
		Timeout: 30 * time.Second,
	}
	resp, err := client.Do(
		req,
	)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(
		io.LimitReader(
			resp.Body,
			10*1024*1024,
		),
	)
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf(
			"HTTP %d: %s",
			resp.StatusCode,
			strings.TrimSpace(
				string(data),
			),
		)
	}
	if out == nil || len(data) == 0 {
		return nil
	}
	if err := json.Unmarshal(
		data,
		out,
	); err != nil {
		return fmt.Errorf(
			"JSON invalide: %w",
			err,
		)
	}
	return nil
}

// Paths are variables only to allow isolated tests. Production values are fixed.
var currentSystemPath = "/run/current-system"
var systemProfilePath = "/nix/var/nix/profiles/system"

func validateBaseline(baseline string) error {
	if filepath.Clean(baseline) != baseline || filepath.Dir(baseline) != "/nix/store" {
		return fmt.Errorf("baseline invalide: %q", baseline)
	}
	info, err := os.Stat(filepath.Join(baseline, "bin", "switch-to-configuration"))
	if err != nil {
		return fmt.Errorf("baseline inaccessible: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0111 == 0 {
		return errors.New("switch-to-configuration baseline non executable")
	}
	return nil
}

func readPermanentBaseline(cfg Config) (string, error) {
	path := filepath.Join(cfg.StateDir, "baseline-system")
	info, err := os.Lstat(path)
	if err != nil {
		return "", fmt.Errorf("baseline permanente manquante; executer install-vm.sh: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0022 != 0 {
		return "", errors.New("baseline-system doit etre un fichier protege")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	baseline := strings.TrimSpace(string(data))
	if err := validateBaseline(baseline); err != nil {
		return "", err
	}
	return baseline, nil
}

func validateWorkspace(workspace string) error {
	if workspace != "/home/exam/workspace" {
		return errors.New("chemin workspace refuse")
	}
	for _, path := range []string{"/home", "/home/exam", workspace} {
		info, err := os.Lstat(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("workspace ou parent non sur: %s", path)
		}
	}
	return nil
}

func stopExamProcesses() error {
	uidText, err := runCommand("/", "id", "-u", "exam")
	if err != nil {
		// Baseline activation can remove the account while retaining its home.
		if _, statErr := os.Stat("/home/exam/workspace"); errors.Is(statErr, os.ErrNotExist) {
			return nil
		}
		uidText, err = runCommand("/", "stat", "-c", "%u", "/home/exam/workspace")
		if err != nil {
			return fmt.Errorf("identification UID exam: %w", err)
		}
	}
	uid, err := strconv.Atoi(strings.TrimSpace(uidText))
	if err != nil || uid <= 0 {
		return errors.New("UID exam invalide; arret refuse")
	}
	// loginctl can return an error for an account without an active login.
	if _, err := exec.LookPath("loginctl"); err == nil {
		_, _ = runCommand("/", "loginctl", "terminate-user", "exam")
	}
	pgrep, err := exec.LookPath("pgrep")
	if err != nil {
		return errors.New("pgrep requis pour verifier l'arret etudiant")
	}
	check := func() (bool, error) {
		output, err := exec.Command(pgrep, "-u", uidText).CombinedOutput()
		if err == nil {
			return strings.TrimSpace(string(output)) != "", nil
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
			return false, nil
		}
		return false, fmt.Errorf("pgrep: %v: %s", err, output)
	}
	alive, err := check()
	if err != nil || !alive {
		return err
	}
	if _, err := runCommand("/", "pkill", "-KILL", "-u", uidText); err != nil {
		// A process can exit between pgrep and pkill. The final check decides.
		log.Printf("pkill exam: %v", err)
	}
	for i := 0; i < 30; i++ {
		alive, err = check()
		if err != nil || !alive {
			return err
		}
		time.Sleep(100 * time.Millisecond)
	}
	return errors.New("processus exam toujours presents; reset refuse")
}

func resetBeforeStart(cfg Config, cmd *Command) error {
	if _, err := os.Lstat(filepath.Join(cfg.StateDir, "pending-submission")); err == nil {
		return errors.New("rendu precedent en attente: relancer END_EXAM avant START_EXAM")
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	archives, err := filepath.Glob(filepath.Join(cfg.StateDir, "archives", "*.zip"))
	if err != nil {
		return err
	}
	if len(archives) != 0 {
		return errors.New("archive de rendu precedente en attente; terminer END_EXAM")
	}
	baseline, err := readPermanentBaseline(cfg)
	if err != nil {
		return err
	}
	if err := validateWorkspace("/home/exam/workspace"); err != nil {
		return err
	}
	if err := stopExamProcesses(); err != nil {
		return err
	}
	// Preserve residual work before resetting. These recovery copies are not
	// submissions and remain outside archives/, so they do not block START.
	entries, err := os.ReadDir("/home/exam/workspace")
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if len(entries) != 0 {
		backupCfg := cfg
		backupCfg.StateDir = filepath.Join(cfg.StateDir, "reset-backups", fmt.Sprintf("before-command-%d-%d", cmd.ID, time.Now().UnixNano()))
		previous := &Command{ExamID: "previous-session", StudentNumber: "unknown"}
		backup, err := createWorkspaceArchive(backupCfg, previous)
		if err != nil {
			return fmt.Errorf("sauvegarde avant nettoyage: %w", err)
		}
		log.Printf("RESET previous workspace preserved = %s", backup)
	}
	if err := restoreBaselinePath(baseline); err != nil {
		return err
	}
	if err := cleanWorkspace("/home/exam/workspace"); err != nil {
		return err
	}
	log.Printf("RESET workspace cleaned; baseline verified; ready to prepare new exam")
	return nil
}

func prepareCleanWorkspace() error {
	const workspace = "/home/exam/workspace"
	if err := validateWorkspace(workspace); err != nil {
		return err
	}
	// The generated exam configuration creates the account.
	uidText, err := runCommand("/", "id", "-u", "exam")
	if err != nil {
		return err
	}
	gidText, err := runCommand("/", "id", "-g", "exam")
	if err != nil {
		return err
	}
	uid, err := strconv.Atoi(strings.TrimSpace(uidText))
	if err != nil || uid <= 0 {
		return errors.New("UID exam invalide")
	}
	gid, err := strconv.Atoi(strings.TrimSpace(gidText))
	if err != nil || gid < 0 {
		return errors.New("GID exam invalide")
	}
	if err := os.MkdirAll(workspace, 0700); err != nil {
		return err
	}
	if err := cleanWorkspace(workspace); err != nil {
		return err
	}
	if err := os.Chown(workspace, uid, gid); err != nil {
		return err
	}
	if err := os.Chmod(workspace, 0700); err != nil {
		return err
	}
	log.Printf("workspace prepared: exam uid=%d gid=%d mode=0700", uid, gid)
	return nil
}

// NixOS services have a restricted PATH which can omit the interactive shell's
// system profile. Use dynamic system links so subprocesses still work after a
// baseline/exam switch, preserving the service's original dependencies.
func configureSystemPath() error {
	paths := []string{"/run/current-system/sw/bin", "/run/wrappers/bin", "/nix/var/nix/profiles/default/bin"}
	if existing := os.Getenv("PATH"); existing != "" {
		paths = append(paths, existing)
	}
	return os.Setenv("PATH", strings.Join(paths, string(os.PathListSeparator)))
}
