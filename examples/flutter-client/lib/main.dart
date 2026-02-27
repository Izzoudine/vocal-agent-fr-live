/// vocal-agent-fr-live — Minimal Flutter Client
///
/// Demonstrates WebSocket connection to the voice agent backend
/// with text input/output and audio playback.
///
/// Dependencies to add to pubspec.yaml:
/// ```yaml
/// dependencies:
///   flutter:
///     sdk: flutter
///   web_socket_channel: ^3.0.0
///   record: ^5.1.0
///   audioplayers: ^6.0.0
///   permission_handler: ^11.3.0
/// ```

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const VocalAgentApp());
}

class VocalAgentApp extends StatelessWidget {
  const VocalAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Agent Vocal FR',
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.dark(
          primary: Colors.blue.shade400,
          secondary: Colors.green.shade400,
        ),
      ),
      home: const VocalAgentScreen(),
    );
  }
}

class VocalAgentScreen extends StatefulWidget {
  const VocalAgentScreen({super.key});

  @override
  State<VocalAgentScreen> createState() => _VocalAgentScreenState();
}

class _VocalAgentScreenState extends State<VocalAgentScreen> {
  // Configuration
  static const String agentBaseUrl = 'http://localhost:8765';
  static const String wsBaseUrl = 'ws://localhost:8765/ws';

  // State
  WebSocketChannel? _channel;
  bool _isConnected = false;
  String? _sessionId;
  final List<LogEntry> _logs = [];
  final TextEditingController _textController = TextEditingController();
  final TextEditingController _personalityController = TextEditingController(
    text: 'Tu es un assistant vocal chaleureux et naturel.',
  );
  final TextEditingController _situationController = TextEditingController(
    text: 'Conversation vocale en temps réel.',
  );
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _disconnect();
    _textController.dispose();
    _personalityController.dispose();
    _situationController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  // --- Connection ---

  Future<void> _connect() async {
    try {
      // Create session via REST API
      final response = await http.post(
        Uri.parse('$agentBaseUrl/start-session'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'personality': _personalityController.text,
          'situation': _situationController.text,
          'voice_id': 'fr_FR-melo-voice1',
          'language': 'fr-FR',
          'tts_engine': 'melo',
          'user_id': 'flutter-user',
        }),
      );

      if (response.statusCode != 200) {
        _addLog('error', 'Erreur HTTP: ${response.statusCode}');
        return;
      }

      final data = jsonDecode(response.body);
      _sessionId = data['session_id'];

      // Connect WebSocket
      _channel = WebSocketChannel.connect(
        Uri.parse('$wsBaseUrl/$_sessionId'),
      );

      _channel!.stream.listen(
        (message) {
          if (message is String) {
            _handleJsonMessage(jsonDecode(message));
          } else if (message is List<int>) {
            // Binary audio data
            _addLog('audio', '🔊 Audio reçu (${message.length} octets)');
            // TODO: Play audio using audioplayers or just_audio
          }
        },
        onDone: () {
          setState(() => _isConnected = false);
          _addLog('system', 'Déconnecté');
        },
        onError: (error) {
          _addLog('error', 'Erreur: $error');
          setState(() => _isConnected = false);
        },
      );

      setState(() => _isConnected = true);
      _addLog('system', '✅ Connecté — session: ${_sessionId!.substring(0, 8)}...');
    } catch (e) {
      _addLog('error', 'Connexion échouée: $e');
    }
  }

  void _disconnect() {
    _channel?.sink.close();
    _channel = null;
    setState(() {
      _isConnected = false;
      _sessionId = null;
    });
  }

  // --- Message Handling ---

  void _handleJsonMessage(Map<String, dynamic> msg) {
    switch (msg['type']) {
      case 'session.created':
        _addLog('system', '🎙️ Session prête');
        break;
      case 'transcription':
        _addLog('user', '🗣️ ${msg['text']}');
        break;
      case 'response.text':
        _addLog('agent', '🤖 ${msg['text']}');
        break;
      case 'audio.start':
        _addLog('audio', '🔊 Audio en cours...');
        break;
      case 'audio.end':
        _addLog('audio', '🔇 Audio terminé');
        break;
      case 'error':
        _addLog('error', '❌ ${msg['message']}');
        break;
      default:
        _addLog('system', '[${msg['type']}]');
    }
  }

  // --- Send Text ---

  void _sendText() {
    final text = _textController.text.trim();
    if (text.isEmpty || _channel == null) return;

    _channel!.sink.add(jsonEncode({
      'type': 'input.text',
      'text': text,
    }));

    _addLog('user', '📝 $text');
    _textController.clear();
  }

  // --- Logging ---

  void _addLog(String type, String message) {
    setState(() {
      _logs.add(LogEntry(
        time: TimeOfDay.now().format(context),
        type: type,
        message: message,
      ));
      if (_logs.length > 100) _logs.removeAt(0);
    });

    // Auto-scroll to bottom
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Color _getLogColor(String type) {
    switch (type) {
      case 'user':
        return Colors.blue.shade300;
      case 'agent':
        return Colors.green.shade300;
      case 'error':
        return Colors.red.shade300;
      case 'audio':
        return Colors.purple.shade300;
      default:
        return Colors.grey.shade500;
    }
  }

  // --- UI ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎙️ Agent Vocal FR'),
        actions: [
          Chip(
            label: Text(
              _isConnected ? '● Connecté' : '○ Déconnecté',
              style: TextStyle(
                color: _isConnected ? Colors.green.shade300 : Colors.red.shade300,
                fontSize: 12,
              ),
            ),
            backgroundColor: _isConnected
                ? Colors.green.shade900.withOpacity(0.3)
                : Colors.red.shade900.withOpacity(0.3),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // Config (when disconnected)
            if (!_isConnected) ...[
              TextField(
                controller: _personalityController,
                decoration: const InputDecoration(
                  labelText: 'Personnalité',
                  border: OutlineInputBorder(),
                ),
                maxLines: 2,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _situationController,
                decoration: const InputDecoration(
                  labelText: 'Situation',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _connect,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Se connecter'),
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Input (when connected)
            if (_isConnected) ...[
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _textController,
                      decoration: const InputDecoration(
                        hintText: 'Tapez un message...',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onSubmitted: (_) => _sendText(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _sendText,
                    child: const Text('Envoyer'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: _disconnect,
                    child: const Text('Quitter'),
                  ),
                ],
              ),
              const SizedBox(height: 16),
            ],

            // Logs
            Expanded(
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.grey.shade800),
                ),
                child: _logs.isEmpty
                    ? Center(
                        child: Text(
                          'En attente de connexion...',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      )
                    : ListView.builder(
                        controller: _scrollController,
                        itemCount: _logs.length,
                        itemBuilder: (context, index) {
                          final log = _logs[index];
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2),
                            child: Text.rich(
                              TextSpan(
                                children: [
                                  TextSpan(
                                    text: '${log.time} ',
                                    style: TextStyle(
                                      color: Colors.grey.shade600,
                                      fontSize: 12,
                                      fontFamily: 'monospace',
                                    ),
                                  ),
                                  TextSpan(
                                    text: log.message,
                                    style: TextStyle(
                                      color: _getLogColor(log.type),
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class LogEntry {
  final String time;
  final String type;
  final String message;

  LogEntry({required this.time, required this.type, required this.message});
}
