package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const agentVersion = "0.2.0"

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

		if cmd.Type != "START_EXAM" {
			_ = complete(
				cfg,
				cmd.ID,
				"ERROR",
				"Commande inconnue",
			)

			state = "ERROR"
			continue
		}

		state = processStartExam(
			cfg,
			cmd,
		)
	}
}

func processStartExam(
	cfg Config,
	cmd *Command,
) string {

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

	baseline, err := filepath.EvalSymlinks(
		"/nix/var/nix/profiles/system",
	)
	if err != nil {
		return fmt.Errorf(
			"lecture system profile: %w",
			err,
		)
	}

	if !strings.HasPrefix(
		baseline,
		"/nix/store/",
	) {
		return fmt.Errorf(
			"baseline NixOS invalide: %s",
			baseline,
		)
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

func restoreBaseline(
	cfg Config,
	cmd *Command,
) error {

	runtimeDir := examRuntimeDir(
		cfg,
		cmd,
	)

	baselineFile := filepath.Join(
		runtimeDir,
		"baseline-system",
	)

	data, err := os.ReadFile(
		baselineFile,
	)
	if err != nil {
		return fmt.Errorf(
			"lecture baseline: %w",
			err,
		)
	}

	baseline := strings.TrimSpace(
		string(data),
	)

	if !strings.HasPrefix(
		baseline,
		"/nix/store/",
	) {
		return fmt.Errorf(
			"baseline invalide: %s",
			baseline,
		)
	}

	switchTool := filepath.Join(
		baseline,
		"bin",
		"switch-to-configuration",
	)

	info, err := os.Stat(
		switchTool,
	)
	if err != nil {
		return fmt.Errorf(
			"switch-to-configuration baseline: %w",
			err,
		)
	}

	if info.IsDir() {
		return errors.New(
			"switch-to-configuration invalide",
		)
	}

	output, err := runCommand(
		runtimeDir,
		switchTool,
		"switch",
	)

	if output != "" {
		log.Printf(
			"rollback: %s",
			output,
		)
	}

	if err != nil {
		return fmt.Errorf(
			"rollback systeme: %w",
			err,
		)
	}

	return nil
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
